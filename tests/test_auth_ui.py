import json
from ipaddress import IPv4Address

from aiohttp import WSMsgType
from pytest_toolbox.comparison import AnyInt, RegexStr

from .conftest import Factory


async def test_login(cli, url, factory: Factory, db_conn):
    user = await factory.create_user(login=False)
    r = await cli.post(
        url('auth:login'),
        data=json.dumps({'email': user.email, 'password': user.password}),
        headers={'Content-Type': 'application/json', 'Origin': 'null'},
    )
    obj = await r.json()
    assert obj == {
        'auth_token': RegexStr('.*'),
        'session': {'session_id': AnyInt(), 'ts': AnyInt(), 'name': 'Tes Ting', 'email': 'testing-1@example.com'},
    }
    assert len(cli.session.cookie_jar) == 0
    session_id = obj['session']['session_id']

    r = await cli.post_json(url('ui:auth-token'), data={'auth_token': obj['auth_token']})
    assert len(cli.session.cookie_jar) == 1
    assert await r.json() == {'user_id': await db_conn.fetchval('select id from users')}

    # check it all works
    obj = await cli.get_json(url('ui:list', session_id=session_id))
    assert obj == {'conversations': []}


async def test_logout(cli, db_conn, factory: Factory):
    await factory.create_user(login=True)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert await db_conn.fetchval('select active from auth_sessions')
    assert len(cli.session.cookie_jar) == 1

    await cli.post_json(factory.url('ui:auth-logout'), '')
    assert len(cli.session.cookie_jar) == 0

    s_id, active = await db_conn.fetchrow('select id, active from auth_sessions')
    assert active is False
    r = await db_conn.fetch(
        """
        select ip, action, ua.value as user_agent from auth_session_events e
        join auth_user_agents ua on e.user_agent = ua.id
        where session=$1
        order by e.id
        """,
        s_id,
    )
    assert [dict(e) for e in r] == [
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'login-pw'},
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'logout'},
    ]


async def test_renew_session(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    for i in range(3):
        r = await cli.get(factory.url('ui:list'))
        assert r.status == 200, await r.text()
        assert 'Set-Cookie' not in r.headers, dict(r.headers)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert 1 == await db_conn.fetchval('select count(*) from auth_session_events')

    settings.micro_session_duration = -1

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()
    assert 'Set-Cookie' in r.headers, dict(r.headers)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert 1 == await db_conn.fetchval('select count(*) from auth_user_agents')
    r = await db_conn.fetch(
        """
        select ip, action, ua.value as user_agent from auth_session_events e
        join auth_user_agents ua on e.user_agent = ua.id
        order by e.id
        """
    )
    assert [dict(e) for e in r] == [
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'login-pw'},
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'update'},
    ]


async def test_renew_session_ws(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    await cli.get_json(factory.url('ui:auth-check'))

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert 1 == await db_conn.fetchval('select count(*) from auth_session_events')

    settings.micro_session_duration = -1

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)

    assert msg.type == WSMsgType.close
    assert msg.data == 4401

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert await db_conn.fetchval('select count(*) from auth_session_events') == 1


async def test_no_auth(cli, url):
    obj = await cli.get_json(url('ui:auth-check', session_id=1), status=401)
    assert obj == {'message': 'Authorisation required'}


async def test_session_dead(cli, db_conn, redis, factory: Factory):
    await factory.create_user(login=True)

    await cli.get_json(factory.url('ui:list'))

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')
    redis.set(f'dead-session:{session_id}', b'1')

    obj = await cli.get_json(factory.url('ui:list'), status=401)
    assert obj == {'message': 'Session dead'}


async def test_session_expired(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    await cli.get_json(factory.url('ui:list'))

    assert await db_conn.fetchval('select count(*) from auth_session_events') == 1

    settings.session_expiry = -1

    await cli.get_json(factory.url('ui:list'), status=401)

    r = await db_conn.fetch(
        """
        select ip, action, ua.value as user_agent from auth_session_events e
        join auth_user_agents ua on e.user_agent = ua.id
        order by e.id
        """
    )
    assert [dict(e) for e in r] == [
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'login-pw'},
        {'ip': IPv4Address('127.0.0.1'), 'user_agent': RegexStr('Python.+'), 'action': 'expired'},
    ]


async def test_login_multiple(cli, url, factory: Factory):
    user1 = await factory.create_user()
    user2 = await factory.create_user()

    await factory.create_conv()
    obj = await cli.get_json(url('ui:list', session_id=user1.session_id))
    assert len(obj['conversations']) == 1

    obj = await cli.get_json(url('ui:list', session_id=user2.session_id))
    assert obj == {'conversations': []}

    await cli.post_json(url('ui:auth-logout', session_id=user1.session_id), '')
    assert len(cli.session.cookie_jar) == 1

    obj = await cli.get_json(url('ui:list', session_id=user2.session_id))
    assert obj == {'conversations': []}

    await cli.get_json(url('ui:list', session_id=user1.session_id), status=401)

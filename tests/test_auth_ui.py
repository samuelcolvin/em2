import json

from aiohttp import WSMsgType
from pytest_toolbox.comparison import AnyInt, RegexStr

from .conftest import Factory


async def test_login(cli, url, factory: Factory):
    user = await factory.create_user(login=False)
    r = await cli.post(
        url('auth:login'),
        data=json.dumps({'email': user.email, 'password': user.password}),
        headers={'Content-Type': 'application/json', 'Origin': 'null'},
    )
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {
        'auth_token': RegexStr('.*'),
        'session': {'session_id': AnyInt(), 'ts': AnyInt(), 'name': 'Tes Ting', 'email': 'testing-1@example.com'},
    }
    assert len(cli.session.cookie_jar) == 0
    session_id = obj['session']['session_id']

    r = await cli.post_json(url('ui:auth-token'), data={'auth_token': obj['auth_token']})
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 1
    assert await r.json() == {'status': 'ok'}

    # check it all works
    r = await cli.get(url('ui:list', session_id=session_id))
    assert r.status == 200, await r.text()
    assert await r.json() == {'conversations': []}


async def test_logout(cli, db_conn, factory: Factory):
    await factory.create_user(login=True)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert await db_conn.fetchval('select active from auth_sessions')
    assert len(cli.session.cookie_jar) == 1

    r = await cli.post_json(factory.url('ui:auth-logout'), '')
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 0

    active, events = await db_conn.fetchrow('select active, events from auth_sessions')
    assert active is False
    events = [json.loads(e) for e in events]
    assert events == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'login-pw'},
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'logout'},
    ]


async def test_renew_session(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    for i in range(3):
        r = await cli.get(factory.url('ui:list'))
        assert r.status == 200, await r.text()
        assert 'Set-Cookie' not in r.headers, dict(r.headers)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    events = await db_conn.fetchval('select events from auth_sessions')
    assert len(events) == 1

    settings.micro_session_duration = -1

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()
    assert 'Set-Cookie' in r.headers, dict(r.headers)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    events = await db_conn.fetchval('select events from auth_sessions')
    assert [json.loads(e) for e in events] == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'login-pw'},
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'update'},
    ]


async def test_renew_session_ws(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    events = await db_conn.fetchval('select events from auth_sessions')
    assert len(events) == 1

    settings.micro_session_duration = -1

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text
        assert json.loads(msg.data) == {'user_v': 1}
        debug(dict(ws._response.headers))

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    events = await db_conn.fetchval('select events from auth_sessions')
    assert [json.loads(e) for e in events] == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'login-pw'},
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'update'},
    ]


async def test_no_auth(cli, url):
    r = await cli.get(url('ui:list', session_id=1))
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': 'Authorisation required'}


async def test_session_dead(cli, db_conn, redis, factory: Factory):
    await factory.create_user(login=True)

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')
    redis.set(f'dead-session:{session_id}', b'1')

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': 'Session dead'}


async def test_session_expired(cli, db_conn, settings, factory: Factory):
    await factory.create_user(login=True)

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()

    events = await db_conn.fetchval('select events from auth_sessions')
    assert len(events) == 1

    settings.session_expiry = -1

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 401, await r.text()

    events = await db_conn.fetchval('select events from auth_sessions')
    assert [json.loads(e) for e in events] == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'login-pw'},
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'expired'},
    ]


async def test_login_multiple(cli, url, factory: Factory):
    user1 = await factory.create_user()
    user2 = await factory.create_user()

    await factory.create_conv()
    r = await cli.get(url('ui:list', session_id=user1.session_id))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert len(obj['conversations']) == 1

    r = await cli.get(url('ui:list', session_id=user2.session_id))
    assert r.status == 200, await r.text()
    assert await r.json() == {'conversations': []}

    r = await cli.post_json(url('ui:auth-logout', session_id=user1.session_id), '')
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 1

    r = await cli.get(url('ui:list', session_id=user2.session_id))
    assert r.status == 200, await r.text()
    assert await r.json() == {'conversations': []}

    r = await cli.get(url('ui:list', session_id=user1.session_id))
    assert r.status == 401, await r.text()

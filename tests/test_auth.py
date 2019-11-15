import json
from ipaddress import IPv4Address

from pytest_toolbox.comparison import AnyInt, RegexStr

from .conftest import Factory


async def test_login(cli, url, factory: Factory):
    user = await factory.create_user()
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
    # auth_token is tested in test_auth_ui


async def test_logout(cli, url, db_conn, factory: Factory):
    await factory.create_user()
    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')

    h = {'Authentication': 'testing' * 6}
    data = {'session_id': session_id, 'ip': '1.2.3.4', 'user_agent': 'whatever', 'action': 'logout'}
    r = await cli.post(url('auth:update-session'), json=data, headers=h)
    assert r.status == 200, await r.text()
    data = {'session_id': session_id, 'ip': '255.255.255.1', 'user_agent': None, 'action': 'logout'}
    r = await cli.post(url('auth:finish-session'), json=data, headers=h)
    assert r.status == 200, await r.text()

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    s_id, active = await db_conn.fetchrow('select id, active from auth_sessions')
    assert active is False
    assert 3 == await db_conn.fetchval('select count(*) from auth_user_agents')
    r = await db_conn.fetch(
        """
        select ip, action, ua.value as user_agent from auth_session_events e
        join auth_user_agents ua on e.user_agent = ua.id
        where session=$1
        order by e.id
        """,
        s_id,
    )
    events = [dict(e) for e in r]
    assert events == [
        {'ip': IPv4Address('127.0.0.1'), 'action': 'login-pw', 'user_agent': RegexStr('Python/.+')},
        {'ip': IPv4Address('1.2.3.4'), 'action': 'update', 'user_agent': 'whatever'},
        {'ip': IPv4Address('255.255.255.1'), 'action': 'logout', 'user_agent': ''},
    ]


async def test_logout_invalid(cli, url, db_conn):
    h = {'Authentication': 'testing' * 6}
    data = {'session_id': 123, 'ip': '255.255.255.1', 'user_agent': 'whatever', 'action': 'logout'}
    r = await cli.post(url('auth:finish-session'), json=data, headers=h)
    assert r.status == 400, await r.text()
    assert await r.json() == {'message': 'wrong session id'}
    assert await db_conn.fetchval('select count(*) from auth_session_events') == 0


async def test_logout_invalid_auth(cli, url, db_conn, factory: Factory):
    await factory.create_user()
    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')

    h = {'Authentication': 'testing' * 5}
    r = await cli.post(url('auth:finish-session'), json={'session_id': session_id, 'event': '{"foo": 4}'}, headers=h)
    assert r.status == 403, await r.text()
    assert await r.text() == 'invalid Authentication header'

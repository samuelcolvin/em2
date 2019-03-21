import json

from pytest_toolbox.comparison import AnyInt, RegexStr

from .conftest import Factory


async def test_login(cli, url, factory: Factory):
    user = await factory.create_user()
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
    # auth_token is tested in test_auth_ui


async def test_logout(cli, url, db_conn, factory: Factory):
    await factory.create_user()
    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')

    h = {'Authentication': 'testing' * 6}
    r = await cli.post(url('auth:logout'), json={'session_id': session_id, 'event': '{"foo": 4}'}, headers=h)
    assert r.status == 200, await r.text()

    active, events = await db_conn.fetchrow('select active, events from auth_sessions')
    assert active is False
    events = [json.loads(e) for e in events]
    assert events == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': 'Python/3.7 aiohttp/3.5.4', 'ac': 'login-pw'},
        {'foo': 4},
    ]


async def test_logout_invalid_auth(cli, url, db_conn, factory: Factory):
    await factory.create_user()
    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    session_id = await db_conn.fetchval('select id from auth_sessions')

    h = {'Authentication': 'testing' * 5}
    r = await cli.post(url('auth:logout'), json={'session_id': session_id, 'event': '{"foo": 4}'}, headers=h)
    assert r.status == 403, await r.text()
    assert await r.text() == 'invalid Authentication header'

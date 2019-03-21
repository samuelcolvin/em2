import json

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

    r = await cli.post_json(url('ui:auth-token'), data={'auth_token': obj['auth_token']})
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 1
    obj = await r.json()
    assert obj == {'status': 'ok'}

    # check it all works
    r = await cli.get(url('ui:list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {'count': 0, 'conversations': []}


async def test_logout(cli, url, db_conn, factory: Factory):
    await factory.create_user(login=True)

    assert 1 == await db_conn.fetchval('select count(*) from auth_sessions')
    assert await db_conn.fetchval('select active from auth_sessions')
    assert len(cli.session.cookie_jar) == 1

    r = await cli.post_json(url('ui:auth-logout'), '')
    assert r.status == 200, await r.text()
    assert len(cli.session.cookie_jar) == 0

    active, events = await db_conn.fetchrow('select active, events from auth_sessions')
    assert active is False
    events = [json.loads(e) for e in events]
    assert events == [
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'login-pw'},
        {'ip': '127.0.0.1', 'ts': AnyInt(), 'ua': RegexStr('Python.+'), 'ac': 'logout'},
    ]

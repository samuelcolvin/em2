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
        'session': {'session_id': AnyInt(), 'name': 'Tes Ting', 'email': 'testing-0@example.com'},
    }
    # auth_token is tested in ui

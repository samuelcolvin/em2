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
    assert obj == []

import json

from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

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
        'session': {'session_id': AnyInt(), 'name': 'Tes Ting', 'email': 'testing-1@example.com'},
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


async def test_create_conv(cli, url, factory: Factory, db_conn):
    user = await factory.create_user(login=True)

    r = await cli.post_json(url('ui:create'), {'subject': 'Sub', 'message': 'Msg'})
    assert r.status == 201, await r.text()

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': RegexStr('.{20}'),
        'published': False,
        'creator': user.ui_user_id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'subject': 'Sub',
        'last_action_id': 2,  # add participant, add message
        'snippet': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['snippet']) == {
        'comp': 'message',
        'verb': 'add',
        'email': 'testing-1@example.com',
        'body': 'Msg',
        'prts': 1,
        'msgs': 1,
    }

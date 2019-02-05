import json

from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

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
    user = await factory.create_user()

    r = await cli.post_json(url('ui:create'), {'subject': 'Sub', 'message': 'Msg'})
    assert r.status == 201, await r.text()
    obj = await r.json()
    conv_key = obj['key']
    assert conv_key == RegexStr('.{20}')

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': conv_key,
        'published': False,
        'creator': user.ui_user_id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'last_action_id': 3,  # add participant, add message, publish
        'details': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['details']) == {
        'comp': 'conv',
        'verb': 'add',
        'sub': 'Sub',
        'email': 'testing-1@example.com',
        'body': 'Msg',
        'prts': 1,
        'msgs': 1,
    }


async def test_create_conv_publish(cli, url, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'publish': True})
    assert r.status == 201, await r.text()
    obj = await r.json()
    conv_key = obj['key']
    assert conv_key == RegexStr('.{64}')

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': conv_key,
        'published': True,
        'creator': user.ui_user_id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'last_action_id': 3,  # add participant, add message, publish
        'details': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['details']) == {
        'comp': 'conv',
        'verb': 'publish',
        'sub': 'Sub',
        'email': 'testing-1@example.com',
        'body': 'Msg',
        'prts': 1,
        'msgs': 1,
    }


async def test_conv_list(cli, url, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    r = await cli.get(url('ui:list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == [
        {
            'key': conv.key,
            'created_ts': CloseToNow(),
            'updated_ts': CloseToNow(),
            'published': False,
            'details': {
                'comp': 'conv',
                'verb': 'add',
                'sub': 'Test Subject',
                'email': 'testing-1@example.com',
                'body': 'Test Message',
                'prts': 1,
                'msgs': 1,
            },
        }
    ]


async def test_conv_actions(cli, url, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    r = await cli.get(url('ui:get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == [
        {
            'id': 1,
            'verb': 'add',
            'component': 'participant',
            'ts': CloseToNow(),
            'actor': 'testing-1@example.com',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 2,
            'verb': 'add',
            'component': 'message',
            'ts': CloseToNow(),
            'body': 'Test Message',
            'msg_format': 'markdown',
            'actor': 'testing-1@example.com',
        },
        {
            'id': 3,
            'verb': 'add',
            'component': 'conv',
            'ts': CloseToNow(),
            'body': 'Test Subject',
            'actor': 'testing-1@example.com',
        },
    ]

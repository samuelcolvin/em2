import json
from asyncio import TimeoutError

import pytest
from aiohttp import WSMsgType
from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

from em2.core import ActionModel, ActionTypes, construct_conv

from .conftest import Factory


async def test_create_conv(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg'}, status=201)
    obj = await r.json()
    conv_key = obj['key']
    assert len(conv_key) == 20

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': conv_key,
        'creator': user.id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'publish_ts': None,
        'last_action_id': 3,  # add participant, add message, publish
        'details': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['details']) == {
        'act': 'conv:create',
        'sub': 'Sub',
        'email': 'testing-1@example.com',
        'creator': 'testing-1@example.com',
        'prev': 'Msg',
        'prts': 1,
        'msgs': 1,
    }
    results = await db_conn.fetch(
        """
        select u.email from users as u
        join participants p on u.id = p.user_id
        where p.conv=$1
        """,
        conv['id'],
    )
    participants = [r[0] for r in results]
    assert participants == ['testing-1@example.com']


async def test_create_conv_participants(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(
        factory.url('ui:create'),
        {
            'subject': 'Sub',
            'message': 'Msg',
            'participants': [{'email': 'foobar@example.com', 'name': 'foo bar'}, {'email': 'another@example.com'}],
        },
        status=201,
    )
    obj = await r.json()
    conv_key = obj['key']
    assert len(conv_key) == 20

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': conv_key,
        'creator': user.id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'publish_ts': None,
        'last_action_id': 5,
        'details': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['details']) == {
        'act': 'conv:create',
        'sub': 'Sub',
        'email': 'testing-1@example.com',
        'creator': 'testing-1@example.com',
        'prev': 'Msg',
        'prts': 3,
        'msgs': 1,
    }
    results = await db_conn.fetch(
        """
        select u.email from users as u
        join participants p on u.id = p.user_id
        where p.conv=$1
        """,
        conv['id'],
    )
    participants = {r[0] for r in results}
    assert participants == {'foobar@example.com', 'another@example.com', 'testing-1@example.com'}


async def test_create_conv_publish(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'publish': True}, status=201)
    obj = await r.json()
    conv_key = obj['key']
    assert len(conv_key) == 64

    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    conv = dict(await db_conn.fetchrow('select * from conversations'))
    assert conv == {
        'id': AnyInt(),
        'key': conv_key,
        'creator': user.id,
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'publish_ts': CloseToNow(),
        'last_action_id': 3,  # add participant, add message, publish
        'details': RegexStr(r'\{.*\}'),
    }
    assert json.loads(conv['details']) == {
        'act': 'conv:publish',
        'sub': 'Sub',
        'email': 'testing-1@example.com',
        'creator': 'testing-1@example.com',
        'prev': 'Msg',
        'prts': 1,
        'msgs': 1,
    }


async def test_conv_list(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    obj = await cli.get_json(factory.url('ui:list'))
    assert obj == {
        'conversations': [
            {
                'key': conv.key,
                'created_ts': CloseToNow(),
                'updated_ts': CloseToNow(),
                'publish_ts': None,
                'last_action_id': 3,
                'seen': True,
                'inbox': False,
                'deleted': False,
                'removed': False,
                'spam': False,
                'draft': True,
                'archive': False,
                'sent': False,
                'labels': [],
                'details': {
                    'act': 'conv:create',
                    'sub': 'Test Subject',
                    'email': 'testing-1@example.com',
                    'creator': 'testing-1@example.com',
                    'prev': 'Test Message',
                    'prts': 1,
                    'msgs': 1,
                },
            }
        ]
    }


async def test_labels_conv_list(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()

    label_ids = [await factory.create_label('Label 1'), await factory.create_label('Label 2')]
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', label_ids, conv.id)

    obj = await cli.get_json(factory.url('ui:list'))
    assert len(obj['conversations']) == 1
    assert obj['conversations'][0]['labels'] == label_ids


async def test_conv_actions(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    obj = await cli.get_json(factory.url('ui:get-actions', conv=conv.key))
    assert obj == [
        {
            'id': 1,
            'conv': conv.key,
            'act': 'participant:add',
            'ts': CloseToNow(),
            'actor': 'testing-1@example.com',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 2,
            'conv': conv.key,
            'act': 'message:add',
            'ts': CloseToNow(),
            'body': 'Test Message',
            'msg_format': 'markdown',
            'actor': 'testing-1@example.com',
        },
        {
            'id': 3,
            'conv': conv.key,
            'act': 'conv:create',
            'ts': CloseToNow(),
            'body': 'Test Subject',
            'actor': 'testing-1@example.com',
        },
    ]


async def test_act(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv()

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    obj = await r.json()
    assert obj == {'action_ids': [4]}

    obj = await cli.get_json(factory.url('ui:get-actions', conv=conv.key))
    assert len(obj) == 4
    assert obj[-1] == {
        'id': 4,
        'conv': conv.key,
        'act': 'message:add',
        'ts': CloseToNow(),
        'actor': 'testing-1@example.com',
        'body': 'this is another message',
        'msg_format': 'markdown',
    }


async def test_conv_details(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key))
    assert obj == {
        'key': await db_conn.fetchval('select key from conversations'),
        'created_ts': CloseToNow(),
        'updated_ts': CloseToNow(),
        'publish_ts': None,
        'last_action_id': 3,
        'details': {
            'act': 'conv:create',
            'sub': 'Test Subject',
            'email': 'testing-1@example.com',
            'creator': 'testing-1@example.com',
            'prev': 'Test Message',
            'prts': 1,
            'msgs': 1,
        },
        'seen': True,
        'inbox': False,
        'archive': False,
        'deleted': False,
        'removed': False,
        'spam': False,
        'draft': True,
        'sent': False,
        'labels': [],
    }


async def test_seen(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv()

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert json.loads(msg.data) == {'user_v': 2}

        r = await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})
        obj = await r.json()
        assert obj == {'action_ids': [4]}

        msg = await ws.receive(timeout=0.1)
        msg = json.loads(msg.data)
        assert len(msg['actions']) == 1
        assert msg['actions'][0]['act'] == 'seen'

        r = await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})
        obj = await r.json()
        assert obj == {'action_ids': []}

        with pytest.raises(TimeoutError):  # no ws message sent in this case
            await ws.receive(timeout=0.1)


async def test_create_then_publish(cli, factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    data = {'actions': [{'act': 'message:lock', 'follows': 2}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert {'action_ids': [4]} == await r.json()
    data = {'actions': [{'act': 'message:modify', 'body': 'msg changed', 'follows': 4}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert {'action_ids': [5]} == await r.json()

    obj1 = await construct_conv(conns, user.id, conv.key)
    assert obj1 == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [{'ref': 5, 'body': 'msg changed', 'created': CloseToNow(), 'format': 'markdown', 'active': True}],
        'participants': {'testing-1@example.com': {'id': 1}},
    }
    assert 5 == await db_conn.fetchval('select count(*) from actions where conv=$1', conv.id)

    r = await cli.post_json(factory.url('ui:publish', conv=conv.key), {'publish': True})
    conv_key2 = (await r.json())['key']

    obj2 = await construct_conv(conns, user.id, conv_key2)
    assert obj2 == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [{'ref': 2, 'body': 'msg changed', 'created': CloseToNow(), 'format': 'markdown', 'active': True}],
        'participants': {'testing-1@example.com': {'id': 1}},
    }
    assert 3 == await db_conn.fetchval('select count(*) from actions where conv=$1', conv.id)


async def test_ws_create(cli, factory: Factory, db_conn):
    user = await factory.create_user()
    assert 1 == await db_conn.fetchval('select v from users where id=$1', user.id)
    await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text
        assert not ws.closed
        assert ws.close_code is None
        assert json.loads(msg.data) == {'user_v': 2}

        conv = await factory.create_conv()

        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text
        assert not ws.closed
        assert ws.close_code is None

    msg_data = json.loads(msg.data)
    assert msg_data == {
        'user_v': 3,
        'actions': [
            {
                'id': 1,
                'act': 'participant:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'participant': 'testing-1@example.com',
                'conv': conv.key,
            },
            {
                'id': 2,
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Message',
                'msg_format': 'markdown',
                'conv': conv.key,
            },
            {
                'id': 3,
                'act': 'conv:create',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Subject',
                'conv': conv.key,
            },
        ],
        'conv_details': {
            'act': 'conv:create',
            'sub': 'Test Subject',
            'email': 'testing-1@example.com',
            'creator': 'testing-1@example.com',
            'prev': 'Test Message',
            'prts': 1,
            'msgs': 1,
        },
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 2, 'sent': 0, 'archive': 0, 'all': 2, 'spam': 0, 'deleted': 0},
    }


async def test_ws_add_msg(cli, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text
        assert json.loads(msg.data) == {'user_v': 2}

        d = {'actions': [{'act': 'message:add', 'body': 'this is another message'}]}
        await cli.post_json(factory.url('ui:act', conv=conv.key), d)

        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text

    msg_data = json.loads(msg.data)
    assert msg_data == {
        'user_v': 3,
        'actions': [
            {
                'id': 4,
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'this is another message',
                'msg_format': 'markdown',
                'conv': conv.key,
            }
        ],
        'conv_details': {
            'act': 'message:add',
            'sub': 'Test Subject',
            'email': 'testing-1@example.com',
            'creator': 'testing-1@example.com',
            'prev': 'this is another message',
            'prts': 1,
            'msgs': 2,
        },
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }


async def test_create_conv_many_participants(cli, factory: Factory):
    await factory.create_user()

    prts = [{f'email': f'p-{i}@example.com'} for i in range(66)]
    r = await cli.post_json(
        factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'participants': prts}, status=400
    )
    assert 'no more than 64 participants permitted' in await r.text()


async def test_act_multiple(cli, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    data = {
        'actions': [
            {'act': 'participant:add', 'participant': 'user-2@example.com'},
            {'act': 'participant:add', 'participant': 'user-3@example.com'},
            {'act': 'participant:add', 'participant': 'user-4@example.com'},
        ]
    }
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    obj = await r.json()
    assert obj == {'action_ids': [4, 5, 6]}
    assert 3 == await db_conn.fetchval('select v from users where id=$1', user.id)


async def test_get_not_participant(factory: Factory, cli):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()
    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key, session_id=user2.session_id), status=404)
    assert obj == {'message': 'Conversation not found'}


async def test_removed_get_list(factory: Factory, cli):
    user1 = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()
    await factory.act(user1.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))
    await factory.act(user1.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='This is a **test**'))

    obj = await cli.get_json(factory.url('ui:list', session_id=user2.session_id))
    assert obj['conversations'][0]['removed'] is False
    assert obj['conversations'][0]['last_action_id'] == 5
    assert obj['conversations'][0]['details']['prev'] == 'This is a test'
    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key, session_id=user2.session_id))
    assert obj['removed'] is False
    assert obj['last_action_id'] == 5
    assert obj['details']['prev'] == 'This is a test'

    await factory.act(user1.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=user2.email, follows=4))
    await factory.act(user1.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='different'))

    obj = await cli.get_json(factory.url('ui:list', session_id=user1.session_id))
    assert obj['conversations'][0]['removed'] is False
    assert obj['conversations'][0]['last_action_id'] == 7
    assert obj['conversations'][0]['details']['prev'] == 'different'
    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key, session_id=user1.session_id))
    assert obj['removed'] is False
    assert obj['last_action_id'] == 7
    assert obj['details']['prev'] == 'different'

    obj = await cli.get_json(factory.url('ui:list', session_id=user2.session_id))
    assert obj['conversations'][0]['removed'] is True
    assert obj['conversations'][0]['last_action_id'] == 6
    assert obj['conversations'][0]['details']['prev'] == 'This is a test'

    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key, session_id=user2.session_id))
    assert obj['removed'] is True
    assert obj['last_action_id'] == 6
    assert obj['details']['prev'] == 'This is a test'

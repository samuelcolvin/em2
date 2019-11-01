import json
from asyncio import TimeoutError

import pytest
from aiohttp import WSMsgType
from arq import Worker
from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

from em2.core import Action, ActionTypes, construct_conv

from .conftest import Em2TestClient, Factory, UserTestClient


async def test_create_conv(cli: UserTestClient, factory: Factory, db_conn):
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
        'leader_node': None,
        'live': True,
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


async def test_create_conv_participants(cli: UserTestClient, factory: Factory, db_conn):
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
        'leader_node': None,
        'live': True,
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


async def test_create_conv_publish(cli: UserTestClient, factory: Factory, db_conn):
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
        'leader_node': None,
        'live': True,
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


async def test_conv_list(cli: UserTestClient, factory: Factory, db_conn):
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


async def test_labels_conv_list(cli: UserTestClient, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()

    label_ids = [await factory.create_label('Label 1'), await factory.create_label('Label 2')]
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', label_ids, conv.id)

    obj = await cli.get_json(factory.url('ui:list'))
    assert len(obj['conversations']) == 1
    assert obj['conversations'][0]['labels'] == label_ids


async def test_conv_actions(cli: UserTestClient, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    obj = await cli.get_json(factory.url('ui:get-actions', conv=conv.key))
    assert obj == [
        {
            'id': 1,
            'act': 'participant:add',
            'ts': CloseToNow(),
            'actor': 'testing-1@example.com',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 2,
            'act': 'message:add',
            'ts': CloseToNow(),
            'body': 'Test Message',
            'msg_format': 'markdown',
            'actor': 'testing-1@example.com',
        },
        {'id': 3, 'act': 'conv:create', 'ts': CloseToNow(), 'body': 'Test Subject', 'actor': 'testing-1@example.com'},
    ]


async def test_act(cli: UserTestClient, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert 4 == await db_conn.fetchval('select id from actions a where act=$1 order by pk desc', 'message:add')

    obj = await cli.get_json(factory.url('ui:get-actions', conv=conv.key))
    assert len(obj) == 4
    assert obj[-1] == {
        'id': 4,
        'act': 'message:add',
        'ts': CloseToNow(),
        'actor': 'testing-1@example.com',
        'body': 'this is another message',
        'msg_format': 'markdown',
    }


async def test_conv_details(cli: UserTestClient, factory: Factory, db_conn):
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


async def test_seen(cli: UserTestClient, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert json.loads(msg.data) == {'user_v': 2}

        r = await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})
        obj = await r.json()
        assert obj == {'interaction': RegexStr(r'[a-f0-9]{32}')}
        assert 4 == await db_conn.fetchval('select id from actions a where act=$1', 'seen')

        msg = await ws.receive(timeout=0.1)
        msg = json.loads(msg.data)
        assert len(msg['actions']) == 1
        assert msg['actions'][0]['act'] == 'seen'

        await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})

        with pytest.raises(TimeoutError):  # no ws message sent in this case
            await ws.receive(timeout=0.1)


async def test_create_then_publish(cli: UserTestClient, factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    data = {'actions': [{'act': 'message:lock', 'follows': 2}]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert 4 == await db_conn.fetchval('select id from actions a where act=$1', 'message:lock')

    data = {'actions': [{'act': 'message:modify', 'body': 'msg changed', 'follows': 4}]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert 5 == await db_conn.fetchval('select id from actions a where act=$1', 'message:modify')

    obj1 = await construct_conv(conns, user.id, conv.key)
    assert obj1 == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 5,
                'author': 'testing-1@example.com',
                'body': 'msg changed',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
                'editors': ['testing-1@example.com'],
            }
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }
    assert 5 == await db_conn.fetchval('select count(*) from actions where conv=$1', conv.id)

    r = await cli.post_json(factory.url('ui:publish', conv=conv.key), {'publish': True})
    conv_key2 = (await r.json())['key']

    obj2 = await construct_conv(conns, user.id, conv_key2)
    assert obj2 == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 2,
                'author': user.email,
                'body': 'msg changed',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            }
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }
    assert 3 == await db_conn.fetchval('select count(*) from actions where conv=$1', conv.id)


async def test_ws_create(cli: UserTestClient, factory: Factory, db_conn):
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
        'user_id': user.id,
        'user_email': user.email,
        'conversation': conv.key,
        'actions': [
            {
                'id': 1,
                'act': 'participant:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'participant': 'testing-1@example.com',
            },
            {
                'id': 2,
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Message',
                'extra_body': False,
                'msg_format': 'markdown',
            },
            {
                'id': 3,
                'act': 'conv:create',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Subject',
                'extra_body': False,
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


async def test_ws_add_msg(cli: UserTestClient, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text
        assert json.loads(msg.data) == {'user_v': 2}

        d = {'actions': [{'act': 'message:add', 'body': 'this is another message'}]}
        r = await cli.post_json(factory.url('ui:act', conv=conv.key), d)
        obj = await r.json()
        interaction = obj['interaction']

        msg = await ws.receive(timeout=0.1)
        assert msg.type == WSMsgType.text

    msg_data = json.loads(msg.data)
    assert msg_data == {
        'user_v': 3,
        'user_id': user.id,
        'user_email': user.email,
        'conversation': conv.key,
        'interaction': interaction,
        'actions': [
            {
                'id': 4,
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'this is another message',
                'extra_body': False,
                'msg_format': 'markdown',
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


async def test_create_conv_many_participants(cli: UserTestClient, factory: Factory):
    await factory.create_user()

    prts = [{f'email': f'p-{i}@example.com'} for i in range(66)]
    r = await cli.post_json(
        factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'participants': prts}, status=400
    )
    assert 'no more than 64 participants permitted' in await r.text()


async def test_act_multiple(cli: UserTestClient, factory: Factory, db_conn, conns):
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

    assert obj == {'interaction': RegexStr(r'[a-f0-9]{32}')}
    assert 3 == await db_conn.fetchval('select v from users where id=$1', user.id)
    assert 4 == await db_conn.fetchval(
        'select a.id from actions a join users u on a.participant_user = u.id where email = $1', 'user-2@example.com'
    )
    assert 5 == await db_conn.fetchval(
        'select a.id from actions a join users u on a.participant_user = u.id where email = $1', 'user-3@example.com'
    )
    assert 6 == await db_conn.fetchval(
        'select a.id from actions a join users u on a.participant_user = u.id where email = $1', 'user-4@example.com'
    )


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
    await factory.act(conv.id, Action(actor_id=user1.id, act=ActionTypes.prt_add, participant=user2.email))
    await factory.act(conv.id, Action(actor_id=user1.id, act=ActionTypes.msg_add, body='This is a **test**'))

    obj = await cli.get_json(factory.url('ui:list', session_id=user2.session_id))
    assert obj['conversations'][0]['removed'] is False
    assert obj['conversations'][0]['last_action_id'] == 5
    assert obj['conversations'][0]['details']['prev'] == 'This is a test'
    obj = await cli.get_json(factory.url('ui:get-details', conv=conv.key, session_id=user2.session_id))
    assert obj['removed'] is False
    assert obj['last_action_id'] == 5
    assert obj['details']['prev'] == 'This is a test'

    await factory.act(
        conv.id, Action(actor_id=user1.id, act=ActionTypes.prt_remove, participant=user2.email, follows=4)
    )
    await factory.act(conv.id, Action(actor_id=user1.id, act=ActionTypes.msg_add, body='different'))

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


async def test_conv_list_live(cli: UserTestClient, factory: Factory, db_conn):
    await factory.create_user()
    await factory.create_conv()

    obj = await cli.get_json(factory.url('ui:list'))
    assert len(obj['conversations']) == 1
    await db_conn.execute('update conversations set live=false')

    obj = await cli.get_json(factory.url('ui:list'))
    assert len(obj['conversations']) == 0


async def test_remote_loader(
    em2_cli: Em2TestClient, cli: UserTestClient, factory: Factory, db_conn, dummy_server, worker: Worker
):
    await em2_cli.create_conv(subject='Testing Remote Leader')
    live, leader_node = await db_conn.fetchrow('select live, leader_node from conversations')
    assert live is True
    assert leader_node == f'localhost:{dummy_server.server.port}/em2'
    obj = await cli.get_json(factory.url('ui:list'))
    assert len(obj['conversations']) == 1
    assert obj['conversations'][0]['details']['sub'] == 'Testing Remote Leader'
    key = obj['conversations'][0]['key']

    data = {'actions': [{'act': 'message:add', 'body': 'reply'}]}
    r = await cli.post_json(factory.url('ui:act', conv=key), data)
    obj = await r.json()
    assert obj  # TODO == {'action_ids': [4, 5, 6]}

    assert await worker.run_check() == 2
    assert len(dummy_server.app['em2_follower_push']) == 1
    push_data = json.loads(dummy_server.app['em2_follower_push'][0]['body'])
    assert push_data == {
        'upstream_em2_node': f'localhost:{em2_cli.server.port}/em2',
        'upstream_signature': RegexStr(r'[a-f0-9]{128}'),
        'interaction_id': RegexStr(r'[a-f0-9]{32}'),
        'actions': [
            {
                'ts': CloseToNow(),
                'act': 'message:add',
                'actor': 'recipient@example.com',
                'body': 'reply',
                'extra_body': False,
                'msg_format': 'markdown',
            }
        ],
    }

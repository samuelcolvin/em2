import json
from asyncio import TimeoutError

import pytest
from aiohttp import WSMsgType
from buildpg import MultipleValues, Values
from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

from em2.core import construct_conv

from .conftest import Factory


async def test_create_conv(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg'})
    assert r.status == 201, await r.text()
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
    )
    assert r.status == 201, await r.text()
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

    r = await cli.post_json(factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'publish': True})
    assert r.status == 201, await r.text()
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
        'prev': 'Msg',
        'prts': 1,
        'msgs': 1,
    }


async def test_conv_list(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {
        'count': 1,
        'conversations': [
            {
                'key': conv.key,
                'created_ts': CloseToNow(),
                'updated_ts': CloseToNow(),
                'publish_ts': None,
                'last_action_id': 3,
                'seen': True,
                'inbox': True,
                'deleted': False,
                'spam': False,
                'labels': [],
                'details': {
                    'act': 'conv:create',
                    'sub': 'Test Subject',
                    'email': 'testing-1@example.com',
                    'prev': 'Test Message',
                    'prts': 1,
                    'msgs': 1,
                },
            }
        ],
    }


async def test_labels_conv_list(cli, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    result = await db_conn.fetch_b(
        'insert into labels (:values__names) values :values returning id',
        values=MultipleValues(Values(user_id=user.id, name='Testing 1'), Values(user_id=user.id, name='Testing 2')),
    )
    label_ids = [r[0] for r in result]
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', label_ids, conv.id)

    r = await cli.get(factory.url('ui:list'))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert len(obj['conversations']) == 1
    assert obj['conversations'][0]['labels'] == label_ids


@pytest.mark.parametrize(
    'query, expected',
    [
        ({}, ['anne', 'ben', 'charlie', 'dave']),
        ({'labels_all': 'label1'}, ['ben', 'dave']),
        ([('labels_all', 'label1'), ('labels_all', 'label2')], ['dave']),
        ([('labels_any', 'label1'), ('labels_any', 'label2')], ['ben', 'charlie', 'dave']),
        ({'inbox': 'true'}, ['anne', 'charlie', 'dave']),
        ({'inbox': 'false'}, ['ben']),
        ({'spam': 'true'}, ['anne']),
        ({'spam': 'false'}, ['ben', 'charlie', 'dave']),
        ({'archive': 'true'}, ['ben']),
    ],
)
async def test_filter_labels_conv_list(cli, factory: Factory, db_conn, query, expected):
    user = await factory.create_user()

    result = await db_conn.fetch_b(
        'insert into labels (:values__names) values :values returning id',
        values=MultipleValues(Values(user_id=user.id, name='Label 1'), Values(user_id=user.id, name='Label 2')),
    )
    label1, label2 = [r[0] for r in result]

    conv_anne = await factory.create_conv(subject='anne')
    await db_conn.execute('update participants set spam=true where conv=$1', conv_anne.id)

    conv_ben = await factory.create_conv(subject='ben')
    await db_conn.execute('update participants set label_ids=$1, inbox=false where conv=$2', [label1], conv_ben.id)

    conv_charlie = await factory.create_conv(subject='charlie')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label2], conv_charlie.id)

    conv_dave = await factory.create_conv(subject='dave')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1, label2], conv_dave.id)

    assert 4 == await db_conn.fetchval('select count(*) from conversations')

    url = str(factory.url('ui:list', query=query)).replace('label1', str(label1)).replace('label2', str(label2))
    r = await cli.get(url)
    assert r.status == 200, await r.text()
    response = [c['details']['sub'] for c in (await r.json())['conversations']]
    assert response == expected, f'url: {url}, response: {response}'


async def test_conv_actions(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    r = await cli.get(factory.url('ui:get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
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
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {'action_ids': [4]}

    r = await cli.get(factory.url('ui:get', conv=conv.key))
    assert r.status == 200, await r.text()
    obj = await r.json()
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


async def test_seen(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv()

    async with cli.session.ws_connect(cli.make_url(factory.url('ui:websocket'))) as ws:
        msg = await ws.receive(timeout=0.1)
        assert json.loads(msg.data) == {'user_v': 2}

        r = await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})
        assert r.status == 200, await r.text()
        obj = await r.json()
        assert obj == {'action_ids': [4]}

        msg = await ws.receive(timeout=0.1)
        msg = json.loads(msg.data)
        assert len(msg['actions']) == 1
        assert msg['actions'][0]['act'] == 'seen'

        r = await cli.post_json(factory.url('ui:act', conv=conv.key), {'actions': [{'act': 'seen'}]})
        assert r.status == 200, await r.text()
        obj = await r.json()
        assert obj == {'action_ids': []}

        with pytest.raises(TimeoutError):  # no ws message sent in this case
            await ws.receive(timeout=0.1)


async def test_create_then_publish(cli, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    data = {'actions': [{'act': 'message:lock', 'follows': 2}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert r.status == 200, await r.text()
    assert {'action_ids': [4]} == await r.json()
    data = {'actions': [{'act': 'message:modify', 'body': 'msg changed', 'follows': 4}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    assert r.status == 200, await r.text()
    assert {'action_ids': [5]} == await r.json()

    obj1 = await construct_conv(db_conn, user.id, conv.key)
    assert obj1 == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [{'ref': 5, 'body': 'msg changed', 'created': CloseToNow(), 'format': 'markdown', 'active': True}],
        'participants': {'testing-1@example.com': {'id': 1}},
    }
    assert 5 == await db_conn.fetchval('select count(*) from actions where conv=$1', conv.id)

    r = await cli.post_json(factory.url('ui:publish', conv=conv.key), {'publish': True})
    assert r.status == 200, await r.text()
    conv_key2 = (await r.json())['key']

    obj2 = await construct_conv(db_conn, user.id, conv_key2)
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
            'prev': 'Test Message',
            'prts': 1,
            'msgs': 1,
        },
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
        r = await cli.post_json(factory.url('ui:act', conv=conv.key), d)
        assert r.status == 200, await r.text()

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
            'prev': 'this is another message',
            'prts': 1,
            'msgs': 2,
        },
    }


async def test_create_conv_many_participants(cli, factory: Factory):
    await factory.create_user()

    prts = [{f'email': f'p-{i}@example.com'} for i in range(66)]
    r = await cli.post_json(factory.url('ui:create'), {'subject': 'Sub', 'message': 'Msg', 'participants': prts})
    assert r.status == 400, await r.text()
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
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj == {'action_ids': [4, 5, 6]}
    assert 3 == await db_conn.fetchval('select v from users where id=$1', user.id)

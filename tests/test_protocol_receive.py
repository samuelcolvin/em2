import json
from datetime import datetime, timezone

import pytest
from arq import ArqRedis
from atoolbox.test_utils import DummyServer
from pytest_toolbox.comparison import CloseToNow

from em2.background import push_sql_all
from em2.core import ActionTypes, construct_conv, generate_conv_key
from em2.protocol.core import actions_to_body, get_signing_key

from .conftest import Em2TestClient, Factory, Worker


async def test_signing_verification(cli, url):
    obj = await cli.get_json(url('protocol:signing-verification'))
    assert obj == {'keys': [{'key': 'd759793bbc13a2819a827c76adb6fba8a49aee007f49f2d0992d99b825ad2c48', 'ttl': 86400}]}


async def test_push(em2_cli: Em2TestClient, settings, dummy_server: DummyServer, db_conn, redis, factory: Factory):
    user = await factory.create_user(email='recipient@example.com')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    conv_key = '8d69cb97ea2607ad5dcead82e7373d159289db11f9709c126e0ef8b2cf324d82'
    assert conv_key == generate_conv_key('actor@em2-ext.example.com', ts, 'Test Subject')
    post_data = {
        'actions': [
            {
                'id': 1,
                'act': 'participant:add',
                'ts': ts.isoformat(),
                'actor': 'actor@em2-ext.example.com',
                'participant': 'actor@em2-ext.example.com',
            },
            {
                'id': 2,
                'act': 'participant:add',
                'ts': ts.isoformat(),
                'actor': 'actor@em2-ext.example.com',
                'participant': 'recipient@example.com',
            },
            {
                'id': 3,
                'act': 'message:add',
                'ts': ts.isoformat(),
                'actor': 'actor@em2-ext.example.com',
                'body': 'Test Message',
                'extra_body': False,
                'msg_format': 'markdown',
            },
            {
                'id': 4,
                'act': 'conv:publish',
                'ts': ts.isoformat(),
                'actor': 'actor@em2-ext.example.com',
                'body': 'Test Subject',
                'extra_body': False,
            },
        ]
    }
    data = json.dumps(post_data)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-push', conv=conv_key, query={'node': em2_node})
    sign_ts = datetime.utcnow().isoformat()
    to_sign = f'POST http://127.0.0.1:{em2_cli.server.port}{path} {sign_ts}\n{data}'.encode()
    signing_key = get_signing_key(settings.signing_secret_key)
    r = await em2_cli.post(
        path,
        data=data,
        headers={
            'Content-Type': 'application/json',
            'Signature': sign_ts + ',' + signing_key.sign(to_sign).signature.hex(),
        },
    )
    assert r.status == 200, await r.text()

    assert await db_conn.fetchval('select count(*) from conversations') == 1
    conv_id, new_conv_key, creator, publish_ts, last_action_id, leader_node = await db_conn.fetchrow(
        'select id, key, creator, publish_ts, last_action_id, leader_node from conversations'
    )
    assert new_conv_key == conv_key
    assert creator == await db_conn.fetchval('select id from users where email=$1', 'actor@em2-ext.example.com')
    assert publish_ts == ts
    assert last_action_id == 4
    assert leader_node == em2_node
    actions_data = await db_conn.fetchval(push_sql_all, conv_id)
    assert json.loads(actions_data)['actions'] == post_data['actions']
    jobs = await redis.queued_jobs()
    assert len(jobs) == 1
    assert jobs[0].function == 'web_push'
    args = json.loads(jobs[0].args[0])
    assert len(args.pop('actions')) == 4
    assert args == {
        'conversation': conv_key,
        'participants': [{'user_id': user.id, 'user_v': 2, 'user_email': 'recipient@example.com'}],
        'conv_details': {
            'act': 'conv:publish',
            'sub': 'Test Subject',
            'email': 'actor@em2-ext.example.com',
            'creator': 'actor@em2-ext.example.com',
            'prev': 'Test Message',
            'prts': 2,
            'msgs': 1,
        },
    }


async def test_append_to_conv(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    assert await conns.main.fetchval('select count(*) from conversations') == 1

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc).isoformat()
    a = 'actor@em2-ext.example.com'
    actions = [{'id': 5, 'act': 'message:add', 'ts': ts, 'actor': a, 'body': 'another message'}]
    await em2_cli.push_actions(conv_key, actions)

    assert await conns.main.fetchval('select count(*) from conversations') == 1
    user_id = await conns.main.fetchval('select id from users where email=$1', 'recipient@example.com')
    conv = await construct_conv(conns, user_id, conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': '2032-06-06T12:00:00+00:00',
        'messages': [
            {
                'ref': 3,
                'author': a,
                'body': 'test message',
                'created': '2032-06-06T12:00:00+00:00',
                'format': 'markdown',
                'active': True,
            },
            {'ref': 5, 'author': a, 'body': 'another message', 'created': ts, 'format': 'markdown', 'active': True},
        ],
        'participants': {a: {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_create_append(em2_cli, conns, factory: Factory):
    await factory.create_user(email='p1@example.com')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    conv_key = '8d69cb97ea2607ad5dcead82e7373d159289db11f9709c126e0ef8b2cf324d82'
    a = 'actor@em2-ext.example.com'
    assert conv_key == generate_conv_key(a, ts, 'Test Subject')
    actions = [
        {'id': 1, 'act': 'participant:add', 'ts': ts, 'actor': a, 'participant': a},
        {'id': 2, 'act': 'participant:add', 'ts': ts, 'actor': a, 'participant': 'p1@example.com'},
        {'id': 3, 'act': 'participant:add', 'ts': ts, 'actor': a, 'participant': 'another@em2-ext.example.com'},
        {'id': 4, 'act': 'message:add', 'ts': ts, 'actor': a, 'body': 'x'},
        {'id': 5, 'act': 'conv:publish', 'ts': ts, 'actor': a, 'body': 'Test Subject'},
        {'id': 6, 'act': 'message:add', 'ts': ts, 'actor': 'another@em2-ext.example.com', 'body': 'more', 'parent': 4},
    ]
    await em2_cli.push_actions(conv_key, actions)

    assert await conns.main.fetchval('select count(*) from conversations') == 1
    assert await conns.main.fetchval('select count(*) from participants') == 3
    user_id = await conns.main.fetchval('select id from users where email=$1', 'p1@example.com')
    conv = await construct_conv(conns, user_id, conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': '2032-06-06T12:00:00+00:00',
        'messages': [
            {
                'ref': 4,
                'body': 'x',
                'author': a,
                'created': '2032-06-06T12:00:00+00:00',
                'format': 'markdown',
                'active': True,
                'children': [
                    {
                        'ref': 6,
                        'author': 'another@em2-ext.example.com',
                        'body': 'more',
                        'created': '2032-06-06T12:00:00+00:00',
                        'format': 'markdown',
                        'active': True,
                    }
                ],
            }
        ],
        'participants': {
            'actor@em2-ext.example.com': {'id': 1},
            'p1@example.com': {'id': 2},
            'another@em2-ext.example.com': {'id': 3},
        },
    }


async def test_no_participants_on_node(em2_cli: Em2TestClient):
    r = await em2_cli.create_conv(recipient='x@other.com', expected_status=400)
    assert await r.json() == {'message': 'no participants on this em2 node'}


async def test_no_signature(em2_cli, dummy_server: DummyServer):
    a = 'actor@em2-ext.example.com'
    post_data = {'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]}
    data = json.dumps(post_data)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-push', conv='1' * 64, query={'node': em2_node})
    r = await em2_cli.post(path, data=data, headers={'Content-Type': 'application/json'})
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': '"Signature" header not found'}


@pytest.mark.parametrize(
    'sig,message',
    [
        ('x', 'Invalid "Signature" header format'),
        ('foo,bar', 'Invalid "Signature" header format'),
        ('2010-06-01T00:00:00.000000,' + '1' * 128, 'Signature expired'),
        ('{now},aaa', 'Invalid signature format'),
        ('{now},' + 'x' * 128, 'Invalid signature format'),
    ],
)
async def test_invalid_signature_format(em2_cli, dummy_server: DummyServer, sig, message):
    if '{now}' in sig:
        sig = sig.replace('{now}', datetime.utcnow().isoformat())
    a = 'actor@em2-ext.example.com'
    post_data = {'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]}
    data = json.dumps(post_data)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-push', conv='1' * 64, query={'node': em2_node})
    r = await em2_cli.post(path, data=data, headers={'Content-Type': 'application/json', 'Signature': sig})
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': message}


async def test_invalid_signature(em2_cli: Em2TestClient, dummy_server: DummyServer):
    a = 'actor@em2-ext.example.com'
    post_data = {'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]}
    data = json.dumps(post_data)
    sig = datetime.utcnow().isoformat() + ',' + '1' * 128
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-push', conv='1' * 64, query={'node': em2_node})
    r = await em2_cli.post(path, data=data, headers={'Content-Type': 'application/json', 'Signature': sig})
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': 'Invalid signature'}


async def test_no_node(em2_cli: Em2TestClient):
    a = 'actor@em2-ext.example.com'
    post_data = {'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]}
    r = await em2_cli.post_json(em2_cli.url('protocol:em2-push', conv='1' * 64), data=post_data, expected_status=400)
    assert await r.json() == {'message': "'node' get parameter missing"}


async def test_valid_signature_repeat(em2_cli, dummy_server: DummyServer):
    a = 'actor@em2-ext.example.com'
    actions = [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]
    for i in range(3):
        # actual data above is not valid
        r = await em2_cli.push_actions('1' * 64, actions, expected_status=470)
        assert await r.json() == {'message': 'full conversation required'}

    # both verification and routing requests should have been cached
    assert dummy_server.log == [
        'GET /em2/v1/signing/verification/ > 200',
        'GET /v1/route/?email=actor@em2-ext.example.com > 200',
    ]


async def test_failed_verification_request(em2_cli: Em2TestClient, dummy_server: DummyServer):
    a = 'actor@em2-ext.example.com'
    actions = [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]
    em2_node = f'localhost:{dummy_server.server.port}/does-not-exist'
    r = await em2_cli.push_actions('1' * 64, actions, em2_node=em2_node, expected_status=401)
    assert await r.json() == {
        'message': (
            f"error getting signature from "
            f"'localhost:{dummy_server.server.port}/does-not-exist/v1/signing/verification/'"
        )
    }

    assert dummy_server.log == ['GET /does-not-exist/v1/signing/verification/ > 404']


async def test_failed_get_em2_node(em2_cli, dummy_server: DummyServer):
    a = 'actor@error.com'
    actions = [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}]
    r = await em2_cli.push_actions('1' * 64, actions, expected_status=401)

    assert await r.json() == {'message': 'not all actors have an em2 node'}
    assert dummy_server.log == ['GET /em2/v1/signing/verification/ > 200']


async def test_participant_missing(em2_cli, dummy_server: DummyServer):
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a},
        {'id': 2, 'act': 'message:add', 'ts': 123, 'actor': a, 'body': 'xxx', 'participant': a},
    ]
    r = await em2_cli.push_actions('1' * 64, actions, expected_status=400)
    assert await r.json() == {
        'message': 'Invalid Data',
        'details': [{'loc': ['actions', 'participant'], 'msg': 'field required', 'type': 'value_error.missing'}],
    }
    assert dummy_server.log == []


@pytest.mark.parametrize(
    'actions, error',
    [
        ('foobar', 'actions must be a list'),
        (['foobar'], 'invalid action at index 0'),
        ([{'act': 'foobar'}], 'invalid action at index 0'),
        ([], 'at least one action is required'),
        ([{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': 'a@ex.org'}], 'field required'),
        (
            [
                {
                    'id': 1,
                    'act': 'participant:add',
                    'ts': 123,
                    'actor': 'a@ex.org',
                    'body': 'x',
                    'participant': 'a@ex.org',
                }
            ],
            'extra fields not permitted',
        ),
        (
            [
                {'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': 'a1@ex.org', 'participant': 'a@ex.org'},
                {'id': 10, 'act': 'participant:add', 'ts': 123, 'actor': 'a2@ex.org', 'participant': 'a@ex.org'},
            ],
            'action ids do not increment correctly',
        ),
        (
            [{'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a2@ex.org', 'body': 'x'}],
            'when publishing, the first action must have ID=1',
        ),
        (
            [
                {'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': 'a1@ex.org', 'participant': 'a@ex.org'},
                {'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a2@ex.org', 'body': 'x'},
            ],
            'only a single actor should publish conversations',
        ),
        (
            [
                {'id': 1, 'act': 'message:add', 'ts': 123, 'actor': 'a1@ex.org', 'body': 'x'},
                {'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a2@ex.org', 'body': 'x'},
            ],
            'only a single actor should publish conversations',
        ),
        (
            [
                {'id': 1, 'act': 'message:modify', 'ts': 123, 'actor': 'a@ex.org', 'body': 'x', 'follows': 1},
                {'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a@ex.org', 'body': 'x'},
            ],
            'when publishing, only \\"participant:add\\",',
        ),
        (
            [
                {'act': 'message:add', 'ts': 123, 'actor': 'a@ex.org', 'body': 'x'},
                {'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a@ex.org', 'body': 'x'},
            ],
            'action ids may not be null',
        ),
    ],
)
async def test_push_invalid_data(em2_cli, actions, error):
    r = await em2_cli.push_actions('1' * 64, actions, expected_status=400)
    # debug(await r.json())
    assert error in await r.text()


async def test_create_conv_repeat(em2_cli: Em2TestClient, db_conn):
    await em2_cli.create_conv()
    assert await db_conn.fetchval('select count(*) from conversations') == 1
    assert await db_conn.fetchval('select count(*) from actions') == 4
    await em2_cli.create_conv()
    assert await db_conn.fetchval('select count(*) from conversations') == 1
    assert await db_conn.fetchval('select count(*) from actions') == 4


async def test_wrong_node(em2_cli: Em2TestClient, db_conn):
    await em2_cli.create_conv()
    await db_conn.execute("update conversations set leader_node='foobar.com'")

    r = await em2_cli.create_conv(expected_status=400)
    assert await r.json() == {'message': "request em2 node does not match conversation's em2 node"}
    assert await db_conn.fetchval('select count(*) from conversations') == 1


async def test_missing_actions(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [
        {'id': 6, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'another message'}
    ]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=470)
    assert await r.json() == {'message': 'full conversation required'}


async def test_non_em2_actor(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [{'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@example.com', 'body': 'another message'}]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=401)
    assert await r.json() == {'message': 'not all actors have an em2 node'}


async def test_other_platform_em2_actor(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [
        {'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'diff@em2-ext.example.com', 'body': 'another message'}
    ]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=400)
    assert await r.json() == {'message': "not all actors' em2 nodes match the request node"}


async def test_actor_not_in_conv(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [{'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'other@em2-ext.example.com', 'body': 'xx'}]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=400)
    assert await r.json() == {'message': 'actor does not have permission to update this conversation'}


async def test_follows_wrong(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [{'id': 5, 'act': 'subject:lock', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'follows': 123}]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=400)
    assert await r.json() == {'message': '"follows" action not found'}


async def test_repeat_actions(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    actions = [
        {'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'another message'}
    ]
    await em2_cli.push_actions(conv_key, actions)
    await em2_cli.push_actions(conv_key, actions)


async def test_edit_subject(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': 'subject:lock', 'ts': ts, 'actor': a, 'follows': 4},
        {'id': 6, 'act': 'subject:modify', 'ts': ts, 'actor': a, 'follows': 5, 'body': 'new'},
    ]
    await em2_cli.push_actions(conv_key, actions)
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    assert conv['subject'] == 'new'


async def test_lock_release_subject(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv(subject='the subject')
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc)
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': 'subject:lock', 'ts': ts, 'actor': a, 'follows': 4},
        {'id': 6, 'act': 'subject:release', 'ts': ts, 'actor': a, 'follows': 5},
    ]
    await em2_cli.push_actions(conv_key, actions)
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    assert conv['subject'] == 'the subject'


async def test_modify_message(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc).isoformat()
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': 'message:lock', 'ts': ts, 'actor': a, 'follows': 3},
        {'id': 6, 'act': 'message:modify', 'ts': ts, 'actor': a, 'follows': 5, 'body': 'whatever'},
    ]
    await em2_cli.push_actions(conv_key, actions)
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': ts,
        'messages': [
            {
                'ref': 6,
                'author': a,
                'body': 'whatever',
                'created': ts,
                'format': 'markdown',
                'active': True,
                'editors': [a],
            }
        ],
        'participants': {a: {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_delete_message(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc).isoformat()
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': 'message:lock', 'ts': ts, 'actor': a, 'follows': 3},
        {'id': 6, 'act': 'message:delete', 'ts': ts, 'actor': a, 'follows': 5},
    ]
    await em2_cli.push_actions(conv_key, actions)
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': ts,
        'messages': [
            {'ref': 6, 'author': a, 'body': 'test message', 'created': ts, 'format': 'markdown', 'active': False}
        ],
        'participants': {'actor@em2-ext.example.com': {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_prt_remove(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc).isoformat()
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': ActionTypes.prt_add, 'ts': ts, 'actor': a, 'participant': 'a2@example.com'},
        {'id': 6, 'act': ActionTypes.prt_remove, 'ts': ts, 'actor': a, 'participant': 'a2@example.com', 'follows': 5},
    ]
    await em2_cli.push_actions(conv_key, actions)
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': ts,
        'messages': [
            {
                'ref': 3,
                'author': 'actor@em2-ext.example.com',
                'body': 'test message',
                'created': ts,
                'format': 'markdown',
                'active': True,
            }
        ],
        'participants': {'actor@em2-ext.example.com': {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_prt_remove_invalid(em2_cli: Em2TestClient, conns):
    await em2_cli.create_conv()
    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc).isoformat()
    a = 'actor@em2-ext.example.com'
    actions = [
        {'id': 5, 'act': ActionTypes.prt_add, 'ts': ts, 'actor': a, 'participant': 'a2@example.com'},
        {'id': 6, 'act': ActionTypes.prt_remove, 'ts': ts, 'actor': a, 'participant': 'a3@example.com', 'follows': 5},
    ]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=400)
    assert await r.json() == {'message': 'participant not found on conversation'}
    conv = await construct_conv(conns, await conns.main.fetchval('select id from users where email=$1', a), conv_key)
    # a2@example.com hasn't been added to the conversation
    assert conv == {
        'subject': 'Test Subject',
        'created': ts,
        'messages': [
            {'ref': 3, 'author': a, 'body': 'test message', 'created': ts, 'format': 'markdown', 'active': True}
        ],
        'participants': {'actor@em2-ext.example.com': {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_create_with_files(
    em2_cli: Em2TestClient, db_conn, factory: Factory, worker: Worker, dummy_server: DummyServer
):
    files = [
        {
            'hash': '9ed9bf64e48c7b343c6dd5700c3ae57fb517a01bac891fd19c1dab57b23accdc',
            'name': 'testing.txt',
            'content_id': 'a' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 123,
            'download_url': dummy_server.server_name + '/image/?size=123',
        },
        {
            'hash': '2cd3827451fd0fdf29d52743e49930d28228275cb960a25f3a973fe827389e7f',
            'name': 'testing2.txt',
            'content_id': '2' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 456,
            'download_url': dummy_server.server_name + '/image/?size=456',
        },
    ]

    a = 'actor@em2-ext.example.com'
    recipient = 'recipient@example.com'
    await factory.create_user(email=recipient)
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    subject = 'File Test'
    conv_key = generate_conv_key(a, ts, subject)
    actions = [
        {'id': 1, 'act': 'participant:add', 'ts': ts, 'actor': a, 'participant': a},
        {'id': 2, 'act': 'participant:add', 'ts': ts, 'actor': a, 'participant': recipient},
        {'id': 3, 'act': 'message:add', 'ts': ts, 'actor': a, 'body': 'testing', 'files': files},
        {'id': 4, 'act': 'conv:publish', 'ts': ts, 'actor': a, 'body': subject},
    ]
    assert await db_conn.fetchval('select count(*) from files') == 0

    await em2_cli.push_actions(conv_key, actions)

    assert await db_conn.fetchval('select count(*) from files') == 2
    file = await db_conn.fetchrow(
        """
        select name, hash, content_id, error, download_url, storage, a.id as action_id from files f
        join actions a on f.action = a.pk where size=123
        """
    )
    assert dict(file) == {
        'name': 'testing.txt',
        'hash': '9ed9bf64e48c7b343c6dd5700c3ae57fb517a01bac891fd19c1dab57b23accdc',
        'content_id': 'a' * 20,
        'error': None,
        'download_url': dummy_server.server_name + '/image/?size=123',
        'storage': None,
        'action_id': 3,
    }
    assert await worker.run_check() == 3
    storage, error = await db_conn.fetchrow(
        """
        select storage, error from files f
        join actions a on f.action = a.pk where size=123
        """
    )
    assert error is None
    assert storage == f's3://s3_files_bucket.example.com/{conv_key}/{"a" * 20}/testing.txt'


async def test_append_files(em2_cli: Em2TestClient, db_conn, redis: ArqRedis):
    await em2_cli.create_conv()

    conv_key = await db_conn.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc).isoformat()
    file = {
        'hash': '1' * 32,
        'name': 'testing.txt',
        'content_id': 'a' * 20,
        'content_disp': 'inline',
        'content_type': 'text/plain',
        'size': 123,
        'download_url': 'https://example.com/image.png',
    }
    actions = [
        {'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'x', 'files': [file]}
    ]
    assert await db_conn.fetchval('select count(*) from actions') == 4
    assert await db_conn.fetchval('select count(*) from files') == 0
    await em2_cli.push_actions(conv_key, actions)
    assert await db_conn.fetchval('select count(*) from actions') == 5
    assert await db_conn.fetchval('select count(*) from files') == 1

    jobs = await redis.queued_jobs()
    assert len(jobs) == 3  # two web_push and download
    j = next(j for j in jobs if j.function == 'download_push_file')
    assert j.args == (await db_conn.fetchval('select id from conversations'), 'aaaaaaaaaaaaaaaaaaaa')


async def test_download_errors(em2_cli: Em2TestClient, db_conn, dummy_server: DummyServer, worker: Worker):
    await em2_cli.create_conv()

    conv_key = await db_conn.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc).isoformat()
    root = dummy_server.server_name
    files = [
        {
            'hash': '1' * 32,
            'name': '1',
            'content_id': 'a' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 501,
            'download_url': f'{root}/image/?size=501',
        },
        {
            'hash': '1' * 32,
            'name': '2',
            'content_id': 'b' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 200,
            'download_url': f'{root}/status/503/',
        },
        {
            'hash': '1' * 32,
            'name': '3',
            'content_id': 'c' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 200,
            'download_url': f'{root}/image/?size=200',
        },
        {
            'hash': '1' * 32,
            'name': '4',
            'content_id': 'd' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 100,
            'download_url': f'{root}/image/?size=101',
        },
        {
            'hash': '1' * 32,
            'name': '5',
            'content_id': 'e' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 100,
            'download_url': f'{root}/invalid-content-type/',
        },
        {
            'hash': '1' * 32,
            'name': '6',
            'content_id': 'f' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 100,
            'download_url': f'{root}/streamed-response/',
        },
    ]
    actions = [
        {'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'x', 'files': files}
    ]
    await em2_cli.push_actions(conv_key, actions)
    assert await db_conn.fetchval('select count(*) from files') == 6

    worker.retry_jobs = False
    await worker.async_run()
    assert worker.jobs_complete == 4
    assert worker.jobs_failed == 4
    v = await db_conn.fetch(
        'select download_url, storage, error from files f join actions a on f.action = a.pk order by name'
    )
    files = [dict(r) for r in v]
    # debug(files)
    assert files == [
        {'download_url': f'{root}/image/?size=501', 'storage': None, 'error': 'file_too_large'},
        {'download_url': f'{root}/status/503/', 'storage': None, 'error': 'response_503'},
        {'download_url': f'{root}/image/?size=200', 'storage': None, 'error': 'hashes_conflict'},
        {'download_url': f'{root}/image/?size=101', 'storage': None, 'error': 'content_length_not_expected'},
        {'download_url': f'{root}/invalid-content-type/', 'storage': None, 'error': 'content_type_invalid'},
        {'download_url': f'{root}/streamed-response/', 'storage': None, 'error': 'streamed_file_too_large'},
    ]


async def test_duplicate_file_content_id(em2_cli: Em2TestClient, db_conn):
    await em2_cli.create_conv()

    conv_key = await db_conn.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc).isoformat()
    files = [
        {
            'hash': '1' * 32,
            'name': '1',
            'content_id': 'a' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 501,
            'download_url': 'https://example.com/image-1.png',
        },
        {
            'hash': '1' * 32,
            'name': '2',
            'content_id': 'a' * 20,
            'content_disp': 'inline',
            'content_type': 'text/plain',
            'size': 200,
            'download_url': 'https://example.com/image-2.png',
        },
    ]
    actions = [
        {'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'x', 'files': files}
    ]
    r = await em2_cli.push_actions(conv_key, actions, expected_status=400)
    assert await r.json() == {'message': 'duplicate file content_id on action 5'}


async def test_push_with_upstream(em2_cli: Em2TestClient, factory: Factory, conns, dummy_server):
    r, a = 'recipient@example.com', 'actor@em2-ext.example.com'
    user = await factory.create_user(email=r)

    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    conv_key = generate_conv_key(a, ts, 'Test Subject')
    ts_str = ts.isoformat()
    actions = [
        {'id': 1, 'act': 'participant:add', 'ts': ts_str, 'actor': a, 'participant': a},
        {'id': 2, 'act': 'participant:add', 'ts': ts_str, 'actor': a, 'participant': r},
        {'id': 3, 'act': 'message:add', 'ts': ts_str, 'actor': a, 'body': 'Test Message'},
        {'id': 4, 'act': 'conv:publish', 'ts': ts_str, 'actor': a, 'body': 'Test Subject'},
    ]

    to_sign = actions_to_body(conv_key, actions)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': actions,
        'upstream_signature': em2_cli.signing_key.sign(to_sign).signature.hex(),
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-push', conv=conv_key, query={'node': em2_node})
    await em2_cli.post_json(path, data=data)
    conv = await construct_conv(conns, user.id, conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': ts_str,
        'messages': [
            {'ref': 3, 'author': a, 'body': 'Test Message', 'created': ts_str, 'format': 'markdown', 'active': True}
        ],
        'participants': {a: {'id': 1}, r: {'id': 2}},
    }


async def test_follower_push(em2_cli: Em2TestClient, factory: Factory, conns, dummy_server):
    await factory.create_user()
    alt_user = 'user@em2-ext.example.com'
    conv = await factory.create_conv(publish=True, participants=[{'email': alt_user}])

    ts = datetime.now().isoformat()
    actions = [
        {'act': 'message:add', 'ts': ts, 'actor': alt_user, 'body': 'Test Message'},
        {'act': 'message:add', 'ts': ts, 'actor': alt_user, 'body': 'Test another Message'},
    ]
    to_sign = actions_to_body(conv.key, actions)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': actions,
        'upstream_signature': em2_cli.signing_key.sign(to_sign).signature.hex(),
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    await em2_cli.post_json(path, data=data)

    conv = await construct_conv(conns, factory.user.id, conv.key)
    assert conv == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 3,
                'author': factory.user.email,
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
            {
                'ref': 5,
                'author': alt_user,
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
            {
                'ref': 6,
                'author': alt_user,
                'body': 'Test another Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
        ],
        'participants': {factory.user.email: {'id': 1}, alt_user: {'id': 2}},
    }


async def test_follower_push_wrong_leader(em2_cli: Em2TestClient, db_conn, dummy_server):
    await em2_cli.create_conv()

    conv_key = await db_conn.fetchval('select key from conversations')

    alt_user = 'user@em2-ext.example.com'
    ts = datetime.now().isoformat()

    actions = [{'act': 'message:add', 'ts': ts, 'actor': alt_user, 'body': 'Test Message'}]
    to_sign = actions_to_body(conv_key, actions)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': actions,
        'upstream_signature': em2_cli.signing_key.sign(to_sign).signature.hex(),
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }

    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-follower-push', conv=conv_key, query={'node': em2_node})
    r = await em2_cli.post_json(path, data=data, expected_status=400)
    assert await r.json() == {'message': f"conversation leader must be this node, not '{em2_node}'"}


async def test_follower_push_with_id(em2_cli: Em2TestClient, factory: Factory, dummy_server):
    await factory.create_user()
    alt_user = 'user@em2-ext.example.com'
    conv = await factory.create_conv(publish=True, participants=[{'email': alt_user}])

    ts = datetime.now().isoformat()
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': [{'id': 1, 'act': 'message:add', 'ts': ts, 'actor': 'actor@em2-ext.example.com', 'body': 'x'}],
        'upstream_signature': '1' * 128,
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    r = await em2_cli.post_json(path, data=data, expected_status=400)
    assert await r.json() == {
        'message': 'Invalid Data',
        'details': [{'loc': ['actions'], 'msg': 'action ids must be null', 'type': 'value_error'}],
    }


async def test_follower_push_wrong_user(em2_cli: Em2TestClient, factory: Factory, dummy_server):
    await factory.create_user()
    alt_user = 'user@em2-ext.example.com'
    conv = await factory.create_conv(publish=True, participants=[{'email': alt_user}])

    ts = datetime.now().isoformat()
    actions = [{'act': 'message:add', 'ts': ts, 'actor': 'different@em2-ext.example.com', 'body': 'x'}]
    to_sign = actions_to_body(conv.key, actions)
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': actions,
        'upstream_signature': em2_cli.signing_key.sign(to_sign).signature.hex(),
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    r = await em2_cli.post_json(path, data=data, expected_status=400)
    assert await r.json() == {'message': 'actor does not have permission to update this conversation'}


async def test_follower_push_with_upstream(em2_cli: Em2TestClient, factory: Factory, conns, dummy_server):
    actor = 'actor@local.example.com'
    await factory.create_user(email=actor)
    conv = await factory.create_conv(publish=True)
    assert await conns.main.fetchval('select count(*) from actions') == 3

    ts = datetime.now().isoformat()
    actions = [{'act': 'message:add', 'ts': ts, 'actor': actor, 'body': 'Test Message'}]
    to_sign = actions_to_body(conv.key, actions)
    data = {
        'actions': actions,
        'upstream_signature': em2_cli.signing_key.sign(to_sign).signature.hex(),
        'upstream_em2_node': f'localhost:{em2_cli.server.port}/em2',
        'interaction_id': '1' * 32,
    }
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    await em2_cli.post_json(path, data=data)
    assert await conns.main.fetchval('select count(*) from actions') == 4


async def test_follower_push_bad_sig(em2_cli: Em2TestClient, factory: Factory, conns, dummy_server):
    await factory.create_user()
    alt_user = 'user@em2-ext.example.com'
    conv = await factory.create_conv(publish=True, participants=[{'email': alt_user}])

    ts = datetime.now().isoformat()
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': [{'act': 'message:add', 'ts': ts, 'actor': alt_user, 'body': 'Test Message'}],
        'upstream_signature': '1' * 128,
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    r = await em2_cli.post_json(path, data=data, expected_status=401)
    assert await r.json() == {'message': 'Upstream signature: Invalid signature'}


async def test_follower_push_no_sig(em2_cli: Em2TestClient, factory: Factory, conns, dummy_server):
    await factory.create_user()
    alt_user = 'user@em2-ext.example.com'
    conv = await factory.create_conv(publish=True, participants=[{'email': alt_user}])

    ts = datetime.now().isoformat()
    em2_node = f'localhost:{dummy_server.server.port}/em2'
    data = {
        'actions': [{'act': 'message:add', 'ts': ts, 'actor': alt_user, 'body': 'Test Message'}],
        'upstream_em2_node': em2_node,
        'interaction_id': '1' * 32,
    }
    path = em2_cli.url('protocol:em2-follower-push', conv=conv.key, query={'node': em2_node})
    r = await em2_cli.post_json(path, data=data, expected_status=400)
    assert await r.json() == {
        'message': 'Invalid Data',
        'details': [{'loc': ['upstream_signature'], 'msg': 'field required', 'type': 'value_error.missing'}],
    }

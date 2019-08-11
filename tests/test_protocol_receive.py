import json
from datetime import datetime, timezone

import pytest
from atoolbox.test_utils import DummyServer

from em2.background import push_sql_all
from em2.core import construct_conv
from em2.protocol.core import get_signing_key

from .conftest import Em2TestClient


async def test_signing_verification(cli, url):
    obj = await cli.get_json(url('protocol:signing-verification'))
    assert obj == {'keys': [{'key': 'd759793bbc13a2819a827c76adb6fba8a49aee007f49f2d0992d99b825ad2c48', 'ttl': 86400}]}


async def test_push(em2_cli, url, settings, dummy_server: DummyServer, db_conn):
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    # key = generate_conv_key('actor@example.org', ts, 'Test Subject')
    conv_key = '5771d1016ac9515319a15f9ea4621b411a2eab8b781e88db9885a806ee12144c'
    em2_node = dummy_server.server_name + '/em2'
    post_data = {
        'conversation': conv_key,
        'em2_node': em2_node,
        'actions': [
            {
                'id': 1,
                'act': 'participant:add',
                'ts': ts.isoformat(),
                'actor': 'actor@example.org',
                'participant': 'actor@example.org',
            },
            {
                'id': 2,
                'act': 'participant:add',
                'ts': ts.isoformat(),
                'actor': 'actor@example.org',
                'participant': 'recipient@example.com',
            },
            {
                'id': 3,
                'act': 'message:add',
                'ts': ts.isoformat(),
                'actor': 'actor@example.org',
                'body': 'Test Message',
                'extra_body': False,
                'msg_format': 'markdown',
            },
            {
                'id': 4,
                'act': 'conv:publish',
                'ts': ts.isoformat(),
                'actor': 'actor@example.org',
                'body': 'Test Subject',
                'extra_body': False,
            },
        ],
    }
    data = json.dumps(post_data)
    path = url('protocol:em2-push')
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
    assert creator == await db_conn.fetchval('select id from users where email=$1', 'actor@example.org')
    assert publish_ts == ts
    assert last_action_id == 4
    assert leader_node == em2_node
    actions_data = await db_conn.fetchval(push_sql_all, conv_id)
    assert json.loads(actions_data)['actions'] == post_data['actions']


async def test_append_to_conv(em2_cli: Em2TestClient, url, conns, dummy_server):
    await em2_cli.create_conv()

    assert await conns.main.fetchval('select count(*) from conversations') == 1

    conv_key = await conns.main.fetchval('select key from conversations')
    ts = datetime(2032, 6, 6, 13, 0, tzinfo=timezone.utc).isoformat()
    data = {
        'conversation': conv_key,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 5, 'act': 'message:add', 'ts': ts, 'actor': 'actor@example.org', 'body': 'another message'}],
    }
    await em2_cli.post_json(url('protocol:em2-push'), data=data)

    assert await conns.main.fetchval('select count(*) from conversations') == 1
    user_id = await conns.main.fetchval('select id from users where email=$1', 'recipient@example.com')
    conv = await construct_conv(conns, user_id, conv_key)
    assert conv == {
        'subject': 'Test Subject',
        'created': '2032-06-06T12:00:00+00:00',
        'messages': [
            {
                'ref': 3,
                'body': 'test message',
                'created': '2032-06-06T12:00:00+00:00',
                'format': 'markdown',
                'active': True,
            },
            {'ref': 5, 'body': 'another message', 'created': ts, 'format': 'markdown', 'active': True},
        ],
        'participants': {'actor@example.org': {'id': 1}, 'recipient@example.com': {'id': 2}},
    }


async def test_create_append(em2_cli, url, dummy_server: DummyServer, conns):
    ts = datetime(2032, 6, 6, 12, 0, tzinfo=timezone.utc)
    # key = generate_conv_key('actor@example.org', ts, 'Test Subject')
    conv_key = '5771d1016ac9515319a15f9ea4621b411a2eab8b781e88db9885a806ee12144c'
    ts_str = ts.isoformat()
    a = 'actor@example.org'
    post_data = {
        'conversation': conv_key,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [
            {'id': 1, 'act': 'participant:add', 'ts': ts_str, 'actor': a, 'participant': a},
            {'id': 2, 'act': 'participant:add', 'ts': ts_str, 'actor': a, 'participant': 'p1@example.com'},
            {'id': 3, 'act': 'participant:add', 'ts': ts_str, 'actor': a, 'participant': 'another@example.org'},
            {'id': 4, 'act': 'message:add', 'ts': ts_str, 'actor': a, 'body': 'x'},
            {'id': 5, 'act': 'conv:publish', 'ts': ts_str, 'actor': a, 'body': 'Test Subject'},
            {'id': 6, 'act': 'message:add', 'ts': ts_str, 'actor': 'another@example.org', 'body': 'more', 'parent': 4},
        ],
    }
    await em2_cli.post_json(url('protocol:em2-push'), post_data)

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
                'created': '2032-06-06T12:00:00+00:00',
                'format': 'markdown',
                'active': True,
                'children': [
                    {
                        'ref': 6,
                        'body': 'more',
                        'created': '2032-06-06T12:00:00+00:00',
                        'format': 'markdown',
                        'active': True,
                    }
                ],
            }
        ],
        'participants': {'actor@example.org': {'id': 1}, 'p1@example.com': {'id': 2}, 'another@example.org': {'id': 3}},
    }


async def test_no_signature(em2_cli, url, dummy_server: DummyServer):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    r = await em2_cli.post(url('protocol:em2-push'), data=data, headers={'Content-Type': 'application/json'})
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': '"Signature" header not found'}


@pytest.mark.parametrize(
    'sig,message',
    [
        ('x', 'Invalid "Signature" header format'),
        ('foo,bar', 'Invalid "Signature" header format'),
        ('2010-06-01T00:00:00.000000,aaa', 'Invalid "Signature" header format'),
        ('2010-06-01T00:00:00.000000,' + 'x' * 128, 'Invalid "Signature" header format'),
        ('2010-06-01T00:00:00.000000,' + '1' * 128, 'Signature expired'),
    ],
)
async def test_invalid_signature_format(em2_cli, url, dummy_server: DummyServer, sig, message):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    r = await em2_cli.post(
        url('protocol:em2-push'), data=data, headers={'Content-Type': 'application/json', 'Signature': sig}
    )
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': message}


async def test_invalid_signature(em2_cli, url, dummy_server: DummyServer, settings):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    sig = datetime.utcnow().isoformat() + ',' + '1' * 128
    r = await em2_cli.post(
        url('protocol:em2-push'), data=data, headers={'Content-Type': 'application/json', 'Signature': sig}
    )
    assert r.status == 401, await r.text()
    assert await r.json() == {'message': 'Invalid signature'}


async def test_valid_signature_repeat(em2_cli, url, dummy_server: DummyServer, settings):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    path = url('protocol:em2-push')
    for i in range(3):
        # actual data above is not valid
        r = await em2_cli.post_json(path, data, status=470)
        assert await r.json() == {'message': 'full conversation required'}

    # both verification and routing requests should have been cached
    assert dummy_server.log == ['GET em2/v1/signing/verification', 'GET v1/route']


async def test_failed_verification_request(cli, url, dummy_server: DummyServer, settings):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/does-not-exist',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    path = url('protocol:em2-push')
    sign_ts = datetime.utcnow().isoformat()
    to_sign = f'POST http://127.0.0.1:{cli.server.port}{path} {sign_ts}\n{data}'.encode()
    signing_key = get_signing_key(settings.signing_secret_key)
    sig = sign_ts + ',' + signing_key.sign(to_sign).signature.hex()
    r = await cli.post(path, data=data, headers={'Content-Type': 'application/json', 'Signature': sig})
    assert r.status == 401, await r.text()
    assert await r.json() == {
        'message': f"error getting signature from '{dummy_server.server_name}/does-not-exist/v1/signing/verification/'"
    }

    assert dummy_server.log == ['GET does-not-exist/v1/signing/verification']


async def test_failed_get_em2_node(em2_cli, url, dummy_server: DummyServer):
    a = 'actor@error.com'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [{'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a, 'participant': a}],
    }
    data = json.dumps(post_data)
    r = await em2_cli.post_json(url('protocol:em2-push'), data, status=401)
    assert r.status == 401, await r.text()

    assert await r.json() == {'message': 'not all actors have an em2 nodes'}
    assert dummy_server.log == ['GET em2/v1/signing/verification']


async def test_participant_missing(em2_cli, url, dummy_server: DummyServer):
    a = 'actor@example.org'
    post_data = {
        'conversation': '1' * 20,
        'em2_node': dummy_server.server_name + '/em2',
        'actions': [
            {'id': 1, 'act': 'participant:add', 'ts': 123, 'actor': a},
            {'id': 2, 'act': 'message:add', 'ts': 123, 'actor': a, 'body': 'xxx', 'participant': a},
        ],
    }
    data = json.dumps(post_data)
    r = await em2_cli.post_json(url('protocol:em2-push'), data, status=400)
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
                {'id': 1, 'act': 'message:modify', 'ts': 123, 'actor': 'a1@ex.org', 'body': 'x'},
                {'id': 2, 'act': 'conv:publish', 'ts': 123, 'actor': 'a2@ex.org', 'body': 'x'},
            ],
            'only a single actor should publish conversations',
        ),
    ],
)
async def test_push_invalid_data(em2_cli, url, dummy_server: DummyServer, actions, error):
    post_data = {'conversation': '1' * 20, 'em2_node': dummy_server.server_name + '/em2', 'actions': actions}
    data = json.dumps(post_data)
    r = await em2_cli.post_json(url('protocol:em2-push'), data, status=400)
    assert error in await r.text()

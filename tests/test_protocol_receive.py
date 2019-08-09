import json
from datetime import datetime, timezone

from atoolbox.test_utils import DummyServer

from em2.background import push_sql_all
from em2.protocol.core import get_signing_key


async def test_signing_verification(cli, url):
    obj = await cli.get_json(url('protocol:signing-verification'))
    assert obj == {'keys': [{'key': 'd759793bbc13a2819a827c76adb6fba8a49aee007f49f2d0992d99b825ad2c48', 'ttl': 86400}]}


async def test_push(cli, url, settings, dummy_server: DummyServer, db_conn):
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
    to_sign = f'POST http://127.0.0.1:{cli.server.port}{path} {sign_ts}\n{data}'.encode()
    signing_key = get_signing_key(settings.signing_secret_key)
    r = await cli.post(
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

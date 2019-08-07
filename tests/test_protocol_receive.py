import json
from datetime import datetime

from em2.protocol.core import get_signing_key


async def test_signing_verification(cli, url):
    obj = await cli.get_json(url('protocol:signing-verification'))
    assert obj == {'keys': [{'key': 'd759793bbc13a2819a827c76adb6fba8a49aee007f49f2d0992d99b825ad2c48', 'ttl': 86400}]}


async def test_push(cli, url, settings):
    data = {
        'conversation': 'this needs to be set',
        'platform': 'em2.example.org',
        'actions': [
            {
                'id': 1,
                'act': 'participant:add',
                'ts': '2032-06-06T12:00:00.000000+00:00',
                'actor': 'actor@example.org',
                'participant': 'actor@example.org',
            },
            {
                'id': 2,
                'act': 'participant:add',
                'ts': '2032-06-06T12:00:00.000000+00:00',
                'actor': 'actor@example.org',
                'participant': 'recipient@example.com',
            },
            {
                'id': 3,
                'act': 'message:add',
                'ts': '2032-06-06T12:00:00.000000+00:00',
                'actor': 'actor@example.org',
                'body': 'Test Message',
                'extra_body': False,
                'msg_format': 'markdown',
            },
            {
                'id': 4,
                'act': 'conv:publish',
                'ts': '2032-06-06T12:00:00.000000+00:00',
                'actor': 'actor@example.org',
                'body': 'Test Subject',
                'extra_body': False,
            },
        ],
    }
    data = json.dumps(data)
    path = url('protocol:em2-push')
    ts = datetime.utcnow().isoformat()
    to_sign = f'POST http://127.0.0.1:{cli.server.port}{path} {ts}\n{data}'.encode()
    signing_key = get_signing_key(settings.signing_secret_key)
    r = await cli.post(
        path,
        data=data,
        headers={'Content-Type': 'application/json', 'Signature': ts + ',' + signing_key.sign(to_sign).signature.hex()},
    )
    assert r.status == 200, await r.text()

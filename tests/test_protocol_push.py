import json

from arq import Worker
from atoolbox.test_utils import DummyServer
from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

from em2.core import Action, ActionTypes
from em2.protocol.core import get_signing_key
from em2.settings import Settings

from .conftest import Factory


async def test_publish_em2(factory: Factory, db_conn, worker: Worker, dummy_server: DummyServer, settings: Settings):
    await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@example.org'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.run_check(max_burst_jobs=2)
    assert await worker.run_check()

    assert len(dummy_server.log) == 3
    data = dummy_server.log.pop()
    assert dummy_server.log == ['GET v1/route', 'POST em2/v1/push']

    ts, sig = data['signature'].split(',')
    assert ts == CloseToNow()

    signing_key = get_signing_key(settings.signing_secret_key)

    to_sign = f'POST {dummy_server.server_name}/em2/v1/push/?domain=localhost {ts}\n{data["body"]}'.encode()
    signing_key.verify_key.verify(to_sign, bytes.fromhex(sig))

    body = json.loads(data['body'])
    assert body == {
        'conversation': conv.key,
        'platform': 'em2.localhost',
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
                'act': 'participant:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'participant': 'whatever@example.org',
            },
            {
                'id': 3,
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Message',
                'extra_body': False,
                'msg_format': 'markdown',
            },
            {
                'id': 4,
                'act': 'conv:publish',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'Test Subject',
                'extra_body': False,
            },
        ],
    }


async def test_publish_ses(factory: Factory, db_conn, ses_worker: Worker, dummy_server):
    await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@example.net'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await ses_worker.async_run()
    assert await ses_worker.run_check() == 3

    assert dummy_server.log == ['POST ses_endpoint_url subject="Test Subject" to="whatever@example.net"']
    assert dummy_server.app['smtp'] == [
        {
            'Subject': 'Test Subject',
            'From': 'testing-1@example.com',
            'To': 'whatever@example.net',
            'EM2-ID': f'{conv.key}-4',
            'MIME-Version': '1.0',
            'Content-Type': RegexStr('multipart/alternative.*'),
            'X-SES-CONFIGURATION-SET': 'em2',
            'part:text/plain': 'Test Message\n',
            'part:text/html': '<p>Test Message</p>\n',
        }
    ]
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    send = dict(await db_conn.fetchrow('select * from sends'))
    assert send == {
        'id': AnyInt(),
        'action': await db_conn.fetchval('select pk from actions where id=4'),
        'ref': 'testing-msg-key',
        'node': None,
        'complete': False,
        'outbound': True,
        'storage': None,
    }


async def test_add_msg_ses(factory: Factory, db_conn, ses_worker: Worker, dummy_server):
    user = await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@example.net'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await ses_worker.async_run()
    assert await ses_worker.run_check() == 3

    action = Action(act=ActionTypes.msg_add, body='This is **another** message')
    assert [5] == await factory.act(user.id, conv.id, action)

    await ses_worker.async_run()
    assert await ses_worker.run_check() == 6

    assert dummy_server.log == [
        'POST ses_endpoint_url subject="Test Subject" to="whatever@example.net"',
        'POST ses_endpoint_url subject="Test Subject" to="whatever@example.net"',
    ]
    assert len(dummy_server.app['smtp']) == 2
    assert dummy_server.app['smtp'][0]['part:text/html'] == '<p>Test Message</p>\n'
    assert dummy_server.app['smtp'][1]['part:text/html'] == '<p>This is <strong>another</strong> message</p>\n'
    assert 2 == await db_conn.fetchval('select count(*) from sends')


async def test_ignore_seen(factory: Factory, db_conn, ses_worker: Worker, dummy_server):
    user = await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@example.net'}], publish=True)
    await ses_worker.async_run()
    assert await ses_worker.run_check() == 3

    await factory.act(user.id, conv.id, Action(act=ActionTypes.prt_add, participant='another@example.net'))
    user2_id = await db_conn.fetchval('select id from users where email=$1', 'another@example.net')

    await ses_worker.async_run()
    assert await ses_worker.run_check() == 6

    await factory.act(user2_id, conv.id, Action(act=ActionTypes.seen))

    assert await ses_worker.run_check() == 8

    assert dummy_server.log == [
        'POST ses_endpoint_url subject="Test Subject" to="whatever@example.net"',
        'POST ses_endpoint_url subject="Test Subject" to="another@example.net,whatever@example.net"',
    ]
    assert len(dummy_server.app['smtp']) == 2
    assert dummy_server.app['smtp'][0]['part:text/html'] == '<p>Test Message</p>\n'
    assert dummy_server.app['smtp'][1]['part:text/html'] == (
        '<p>The following people have been added to the conversation: another@example.net</p>\n'
    )

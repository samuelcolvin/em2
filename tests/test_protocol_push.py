from arq import Worker
from pytest_toolbox.comparison import AnyInt, RegexStr

from em2.core import ActionModel, ActionTypes

from .conftest import Factory


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

    action = ActionModel(act=ActionTypes.msg_add, body='This is **another** message')
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

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant='another@example.net'))
    user2_id = await db_conn.fetchval('select id from users where email=$1', 'another@example.net')

    await ses_worker.async_run()
    assert await ses_worker.run_check() == 6

    await factory.act(user2_id, conv.id, ActionModel(act=ActionTypes.seen))

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

from arq import Worker
from pytest_toolbox.comparison import AnyInt, RegexStr

from em2.core import ActionModel, ActionTypes

from .conftest import Factory


async def test_publish_ses(factory: Factory, db_conn, ses_worker: Worker, dummy_server):
    await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await ses_worker.async_run()
    assert (ses_worker.jobs_complete, ses_worker.jobs_failed, ses_worker.jobs_retried) == (2, 0, 0)

    assert dummy_server.log == ['POST ses_endpoint subject="Test Subject" to="whatever@remote.com"']
    assert dummy_server.app['smtp'] == [
        {
            'Subject': 'Test Subject',
            'From': 'testing-1@example.com',
            'To': 'whatever@remote.com',
            'EM2-ID': f'{conv.key}-4',
            'MIME-Version': '1.0',
            'Content-Type': RegexStr('multipart/alternative.*'),
            'part:text/plain': 'Test Message\n',
            'part:text/html': '<p>Test Message</p>\n',
        }
    ]
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    send = dict(await db_conn.fetchrow('select * from sends'))
    assert send == {
        'id': AnyInt(),
        'action': await db_conn.fetchval('select pk from actions where id=4'),
        'ref': 'testing-msg-key@eu-west-1.amazonses.com',
        'node': None,
        'complete': None,
    }


async def test_add_msg_ses(factory: Factory, db_conn, ses_worker: Worker, dummy_server):
    user = await factory.create_user()
    conv = await factory.create_conv(participants=[{'email': 'whatever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await ses_worker.async_run()
    assert (ses_worker.jobs_complete, ses_worker.jobs_failed, ses_worker.jobs_retried) == (2, 0, 0)

    action = ActionModel(act=ActionTypes.msg_add, body='This is **another** message')
    assert [5] == await factory.act(user.id, conv.key, action)

    await ses_worker.async_run()
    assert (ses_worker.jobs_complete, ses_worker.jobs_failed, ses_worker.jobs_retried) == (4, 0, 0)

    assert dummy_server.log == [
        'POST ses_endpoint subject="Test Subject" to="whatever@remote.com"',
        'POST ses_endpoint subject="Test Subject" to="whatever@remote.com"',
    ]
    assert len(dummy_server.app['smtp']) == 2
    assert dummy_server.app['smtp'][0]['part:text/html'] == '<p>Test Message</p>\n'
    assert dummy_server.app['smtp'][1]['part:text/html'] == '<p>This is <strong>another</strong> message</p>\n'
    assert 2 == await db_conn.fetchval('select count(*) from sends')

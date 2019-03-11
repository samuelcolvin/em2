import base64
import email
import json
from datetime import datetime, timezone
from email.message import EmailMessage

from arq import Worker
from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import construct_conv

from .conftest import Factory


async def create_send(factory: Factory, worker: Worker, db_conn):
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'whomever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (2, 0, 0)
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    return await db_conn.fetchrow('select id, ref from sends')


def build_message(
    subject='Test Subject',
    e_from='whomever@remote.com',
    to=('testing-1@example.com',),
    text_body='this is a message.',
    html_body='this is an html <b>message</b>.',
    message_id='message-id@remote.com',
    **headers,
):
    email_msg = EmailMessage()
    email_msg['Message-ID'] = message_id
    email_msg['Subject'] = subject
    email_msg['From'] = e_from
    email_msg['To'] = ','.join(to)
    email_msg['Date'] = email.utils.format_datetime(datetime(2032, 1, 1, 12, 0))

    for k, v in headers.items():
        email_msg[k] = v

    text_body and email_msg.set_content(text_body)
    html_body and email_msg.add_alternative(html_body, subtype='html')
    return base64.b64encode(email_msg.as_string().encode()).decode()


async def test_ses_send_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
    send_id, message_id = await create_send(factory, worker, db_conn)

    data = {
        'Type': 'Notification',
        'Message': json.dumps(
            {'eventType': 'Send', 'mail': {'messageId': message_id, 'timestamp': '2032-10-16T12:00:00.000Z'}}
        ),
    }

    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic dGVzdGluZw=='})
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from send_events where send=$1', send_id)
    r = await db_conn.fetchrow('select * from send_events where send=$1', send_id)
    assert dict(r) == {
        'id': AnyInt(),
        'send': send_id,
        'status': 'Send',
        'ts': datetime(2032, 10, 16, 12, 0, tzinfo=timezone.utc),
        'user_ids': None,
        'extra': None,
    }


async def test_ses_bounce_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
    send_id, message_id = await create_send(factory, worker, db_conn)
    data = {
        'Type': 'Notification',
        'Message': json.dumps(
            {
                'eventType': 'Bounce',
                'bounce': {
                    'bouncedRecipients': [
                        {'emailAddress': factory.user.email, 'foo': 'bar'},
                        {'emailAddress': 'another@remote.com', 'foo': 'bar'},
                    ],
                    'bounceType': 'bouncing-ball',
                    'timestamp': '2032-10-16T12:00:00.000Z',
                },
                'mail': {'messageId': message_id},
            }
        ),
    }

    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic dGVzdGluZw=='})
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from send_events where send=$1', send_id)
    r = await db_conn.fetchrow('select status, user_ids, extra from send_events where send=$1', send_id)
    assert r['status'] == 'Bounce'
    assert r['user_ids'] == [factory.user.id]
    extra = json.loads(r['extra'])
    assert extra == {
        'bounceType': 'bouncing-ball',
        'bouncedRecipients': [
            {'emailAddress': 'testing-1@example.com', 'foo': 'bar'},
            {'emailAddress': 'another@remote.com', 'foo': 'bar'},
        ],
    }


async def test_ses_complaint_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
    send_id, message_id = await create_send(factory, worker, db_conn)
    assert 2 == await db_conn.fetchval('select count(*) from participants where conv=$1', factory.conv.id)
    data = {
        'Type': 'Notification',
        'Message': json.dumps(
            {
                'eventType': 'Complaint',
                'complaint': {
                    'complainedRecipients': [{'emailAddress': 'whomever@remote.com'}],
                    'complaintFeedbackType': 'grumpy',
                    'bounceType': 'bouncing-ball',
                    'timestamp': '2032-10-16T12:00:00.000Z',
                },
                'mail': {'messageId': message_id},
            }
        ),
    }

    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic dGVzdGluZw=='})
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from participants where conv=$1', factory.conv.id)
    user_id = await db_conn.fetchval('select id from users where email=$1', 'whomever@remote.com')
    r = await db_conn.fetchrow('select status, user_ids, extra from send_events where send=$1', send_id)
    assert r['status'] == 'Complaint'
    assert r['user_ids'] == [user_id]
    extra = json.loads(r['extra'])
    assert extra == {'complaintFeedbackType': 'grumpy', 'emails': ['whomever@remote.com']}


async def test_ses_invalid_auth(cli, url):
    data = {'Type': 'Notification'}
    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic bad'})
    assert r.status == 401


async def test_ses_new_email(factory: Factory, db_conn, cli, url):
    await factory.create_user()
    assert 0 == await db_conn.fetchval('select count(*) from sends')
    assert 0 == await db_conn.fetchval('select count(*) from conversations')
    assert 0 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from users')
    data = {'Type': 'Notification', 'Message': json.dumps({'notificationType': 'Received', 'content': build_message()})}
    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic dGVzdGluZw=='})
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    assert 2 == await db_conn.fetchval('select count(*) from users')

    conv_id = await db_conn.fetchval('select id from conversations')
    new_user_id = await db_conn.fetchval('select id from users where email=$1', 'whomever@remote.com')
    obj = await construct_conv(db_conn, new_user_id, conv_id)
    assert obj == {
        'subject': 'Test Subject',
        'created': '2032-01-01T12:00:00+00:00',
        'messages': [
            {
                'ref': 3,
                'body': 'this is an html <b>message</b>.',
                'created': '2032-01-01T12:00:00+00:00',
                'format': 'html',
                'active': True,
            }
        ],
        'participants': {'whomever@remote.com': {'id': 1}, 'testing-1@example.com': {'id': 2}},
    }

    r = await db_conn.fetchrow('select * from sends')
    assert dict(r) == {
        'id': AnyInt(),
        'action': AnyInt(),
        'ref': 'message-id@remote.com',
        'node': None,
        'complete': True,
    }
    action = await db_conn.fetchrow('select id, conv, actor, act from actions where pk=$1', r['action'])
    assert dict(action) == {'id': 1, 'conv': conv_id, 'actor': new_user_id, 'act': 'participant:add'}


async def test_ses_reply(factory: Factory, worker: Worker, db_conn, cli, url):
    send_id, message_id = await create_send(factory, worker, db_conn)
    assert 1 == await db_conn.fetchval('select count(*) from conversations')
    msg_extra = {'html_body': 'This is a <u>reply</u>.', 'In-Reply-To': message_id}
    data = {
        'Type': 'Notification',
        'Message': json.dumps({'notificationType': 'Received', 'content': build_message(**msg_extra)}),
    }
    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic dGVzdGluZw=='})
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    new_user_id = await db_conn.fetchval('select id from users where email=$1', 'whomever@remote.com')
    obj = await construct_conv(db_conn, new_user_id, factory.conv.id)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {'ref': 3, 'body': 'Test Message', 'created': CloseToNow(), 'format': 'markdown', 'active': True},
            {
                'ref': 5,
                'body': 'This is a <u>reply</u>.',
                'created': '2032-01-01T12:00:00+00:00',
                'format': 'html',
                'active': True,
            },
        ],
        'participants': {'testing-1@example.com': {'id': 1}, 'whomever@remote.com': {'id': 2}},
    }

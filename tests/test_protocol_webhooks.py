import json
from datetime import datetime, timezone

from arq import Worker
from pytest_toolbox.comparison import AnyInt

from .conftest import Factory


async def create_send(factory: Factory, worker: Worker, db_conn):
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'whatever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (2, 0, 0)
    assert 1 == await db_conn.fetchval('select count(*) from sends')
    return await db_conn.fetchrow('select id, ref from sends')


async def test_send_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
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


async def test_bounce_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
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


async def test_complaint_webhook(factory: Factory, worker: Worker, db_conn, cli, url):
    send_id, message_id = await create_send(factory, worker, db_conn)
    assert 2 == await db_conn.fetchval('select count(*) from participants where conv=$1', factory.conv.id)
    data = {
        'Type': 'Notification',
        'Message': json.dumps(
            {
                'eventType': 'Complaint',
                'complaint': {
                    'complainedRecipients': [{'emailAddress': 'whatever@remote.com'}],
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
    user_id = await db_conn.fetchval('select id from users where email=$1', 'whatever@remote.com')
    r = await db_conn.fetchrow('select status, user_ids, extra from send_events where send=$1', send_id)
    assert r['status'] == 'Complaint'
    assert r['user_ids'] == [user_id]
    extra = json.loads(r['extra'])
    assert extra == {'complaintFeedbackType': 'grumpy', 'emails': ['whatever@remote.com']}


async def test_invalid_auth(cli, url):
    data = {'Type': 'Notification'}
    r = await cli.post(url('protocol:webhook-ses'), json=data, headers={'Authorization': 'Basic bad'})
    assert r.status == 401

import json
from datetime import datetime, timezone

from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import construct_conv

from .conftest import Factory


async def test_ses_send_webhook(db_conn, cli, url, sns_data, send_to_remote):
    send_id, message_id = send_to_remote

    data = sns_data(
        message_id, eventType='Send', mail={'messageId': message_id, 'timestamp': '2032-10-16T12:00:00.000Z'}
    )

    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
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


async def test_ses_bounce_webhook(factory: Factory, db_conn, cli, url, sns_data, send_to_remote):
    send_id, message_id = send_to_remote
    data = sns_data(
        message_id,
        eventType='Bounce',
        bounce={
            'bouncedRecipients': [
                {'emailAddress': factory.user.email, 'foo': 'bar'},
                {'emailAddress': 'another@remote.com', 'foo': 'bar'},
            ],
            'bounceType': 'bouncing-ball',
            'timestamp': '2032-10-16T12:00:00.000Z',
        },
        mail={'messageId': message_id},
    )

    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
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


async def test_ses_complaint_webhook(factory: Factory, db_conn, cli, url, sns_data, send_to_remote):
    send_id, message_id = send_to_remote
    assert 2 == await db_conn.fetchval('select count(*) from participants where conv=$1', factory.conv.id)
    data = sns_data(
        message_id,
        eventType='Complaint',
        complaint={
            'complainedRecipients': [{'emailAddress': 'whomever@remote.com'}],
            'complaintFeedbackType': 'grumpy',
            'bounceType': 'bouncing-ball',
            'timestamp': '2032-10-16T12:00:00.000Z',
        },
        mail={'messageId': message_id},
    )

    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from participants where conv=$1', factory.conv.id)
    user_id = await db_conn.fetchval('select id from users where email=$1', 'whomever@remote.com')
    r = await db_conn.fetchrow('select status, user_ids, extra from send_events where send=$1', send_id)
    assert r['status'] == 'Complaint'
    assert r['user_ids'] == [user_id]
    extra = json.loads(r['extra'])
    assert extra == {'complaintFeedbackType': 'grumpy', 'emails': ['whomever@remote.com']}


async def test_ses_invalid_sig(cli, url, sns_data):
    data = sns_data('whatever', mock_verify=False, eventType='whatever')
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
    assert r.status == 403


async def test_ses_new_email(factory: Factory, db_conn, cli, url, create_email):
    await factory.create_user()
    assert 0 == await db_conn.fetchval('select count(*) from sends')
    assert 0 == await db_conn.fetchval('select count(*) from conversations')
    assert 0 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from users')

    data = create_email()
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
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
        'outbound': None,
        'storage': None,
    }
    action = await db_conn.fetchrow('select id, conv, actor, act from actions where pk=$1', r['action'])
    assert dict(action) == {'id': 1, 'conv': conv_id, 'actor': new_user_id, 'act': 'participant:add'}


async def test_ses_reply(factory: Factory, db_conn, cli, url, create_email, send_to_remote):
    send_id, message_id = send_to_remote
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    data = create_email(**{'html_body': 'This is a <u>reply</u>.', 'In-Reply-To': message_id})
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
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


async def test_ses_reply_different_email(factory: Factory, db_conn, cli, url, create_email, send_to_remote):
    send_id, message_id = send_to_remote
    assert 1 == await db_conn.fetchval('select count(*) from conversations')

    kwargs = {'e_from': 'different@remote.com', 'html_body': 'This is a <u>reply</u>.', 'In-Reply-To': message_id}
    data = create_email(**kwargs)
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
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
                'ref': 6,
                'body': 'This is a <u>reply</u>.',
                'created': '2032-01-01T12:00:00+00:00',
                'format': 'html',
                'active': True,
            },
        ],
        'participants': {
            'testing-1@example.com': {'id': 1},
            'whomever@remote.com': {'id': 2},
            'different@remote.com': {'id': 5},
        },
    }


async def test_clean_email(factory: Factory, db_conn, cli, url, create_email):
    await factory.create_user()

    data = create_email(
        html_body="""
        <div dir="ltr">this is a reply<br clear="all"/>
        <div class="gmail_quote">
          <div class="gmail_attr" dir="ltr">On Fri, 15 Mar 2019 at 17:00, &lt;<a
                  href="mailto:testing@imber.io">testing@imber.io</a>&gt; wrote:<br/></div>
          <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;padding-left:1ex">
            <p>whatever</p>
          </blockquote>
        </div>
        """
    )
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=data)
    assert r.status == 204, await r.text()
    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    body = await db_conn.fetchval("select body from actions where act='message:add'")
    assert body == '<div dir="ltr">this is a reply<br clear="all"/>\n\n</div>'

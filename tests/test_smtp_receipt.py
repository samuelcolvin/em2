import json

import pytest
from aiohttp.web_exceptions import HTTPGatewayTimeout
from pytest_toolbox.comparison import RegexStr

from em2.core import conv_actions_json
from em2.protocol.views.fallback_utils import process_smtp
from em2.utils.smtp import CopyToTemp

from .conftest import Factory


async def test_clean_email(fake_request, db_conn, create_email, send_to_remote):
    send_id, message_id = send_to_remote

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    msg = create_email(
        html_body="""
        <div dir="ltr">this is a reply<br clear="all"/>
        <div class="gmail_signature">this is a signature</div>
        <div class="gmail_quote">
          <div class="gmail_attr" dir="ltr">On Fri, 15 Mar 2019 at 17:00, &lt;<a
                  href="mailto:testing@imber.io">testing@imber.io</a>&gt; wrote:<br/></div>
          <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;padding-left:1ex">
            <p>whatever</p>
          </blockquote>
        </div>
        """,
        headers={'In-Reply-To': message_id},
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    body = await db_conn.fetchval("select body from actions where act='message:add' order by pk desc limit 1")
    assert body == (
        '<div dir="ltr">this is a reply<br clear="all"/>\n'
        '<div class="gmail_signature">this is a signature</div>\n'
        '</div>'
    )
    assert await db_conn.fetchval("select details->>'prev' from conversations") == 'this is a reply'


async def test_attachment_content_id(fake_request, factory: Factory, db_conn, create_email, attachment, create_image):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[
            attachment(
                'testing.jpeg',
                'image/jpeg',
                create_image(),
                {'Content-ID': 'foobar-123', 'Content-Disposition': 'inline'},
            )
        ],
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    assert 'This is the <b>message</b>.' == await db_conn.fetchval("select body from actions where act='message:add'")

    assert 1 == await db_conn.fetchval("select count(*) from files")
    file = await db_conn.fetchrow(
        'select action, storage, content_disp, hash, content_id, name, content_type from files'
    )
    assert dict(file) == {
        'action': await db_conn.fetchval("select pk from actions where act='message:add'"),
        'storage': None,
        'content_disp': 'inline',
        'hash': 'fc0f9baebcd2abc35d49151df755603d1c52fe4b',
        'content_id': 'foobar-123',
        'name': None,
        'content_type': 'image/jpeg',
    }


async def test_attachment_actions(fake_request, factory: Factory, db_conn, create_email, attachment):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[
            attachment('testing1.txt', 'text/plain', 'hello1'),
            attachment('testing2.txt', 'text/plain', 'hello2', {'Content-ID': 'testing-hello2'}),
        ],
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    assert 'This is the <b>message</b>.' == await db_conn.fetchval("select body from actions where act='message:add'")

    assert 2 == await db_conn.fetchval("select count(*) from files")
    file = await db_conn.fetchrow(
        """
        select action, storage, content_disp, hash, content_id, name, content_type
        from files
        where name='testing1.txt'
        """
    )
    assert dict(file) == {
        'action': await db_conn.fetchval("select pk from actions where act='message:add'"),
        'storage': None,
        'content_disp': 'attachment',
        'hash': '9a712614320fa93e81eca8408f32c9c1fde6bdc1',
        'content_id': '9a712614320fa93e81eca8408f32c9c1fde6bdc1',
        'name': 'testing1.txt',
        'content_type': 'text/plain',
    }
    conv_id = await db_conn.fetchval('select id from conversations')
    data = json.loads(await conv_actions_json(db_conn, factory.user.id, conv_id))
    assert data == [
        {
            'id': 1,
            'conv': RegexStr('.*'),
            'act': 'participant:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'whomever@remote.com',
            'participant': 'whomever@remote.com',
        },
        {
            'id': 2,
            'conv': RegexStr('.*'),
            'act': 'participant:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'whomever@remote.com',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 3,
            'conv': RegexStr('.*'),
            'act': 'message:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'whomever@remote.com',
            'body': 'This is the <b>message</b>.',
            'msg_format': 'html',
            'files': [
                {
                    'content_disp': 'attachment',
                    'hash': '9a712614320fa93e81eca8408f32c9c1fde6bdc1',
                    'content_id': '9a712614320fa93e81eca8408f32c9c1fde6bdc1',
                    'name': 'testing1.txt',
                    'content_type': 'text/plain',
                },
                {
                    'content_disp': 'attachment',
                    'hash': 'a69dd0da865b28d7d215a2ec84623d191059aafe',
                    'content_id': 'testing-hello2',
                    'name': 'testing2.txt',
                    'content_type': 'text/plain',
                },
            ],
        },
        {
            'id': 4,
            'conv': RegexStr('.*'),
            'act': 'conv:publish',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'whomever@remote.com',
            'body': 'Test Subject',
        },
    ]


async def test_get_file(fake_request, factory: Factory, db_conn, create_email, attachment, cli, dummy_server):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[attachment('testing.txt', 'text/plain', 'hello', {'Content-ID': 'testing-hello2'})],
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/s3-test-path')

    assert 1 == await db_conn.fetchval("select count(*) from files")

    conv_key = await db_conn.fetchval('select key from conversations')
    data = json.loads(await conv_actions_json(db_conn, factory.user.id, conv_key))
    assert data[2]['files'] == [
        {
            'content_disp': 'attachment',
            'hash': '874f36549f57ff5d6596dd153cb94524f1eeebc1',
            'content_id': 'testing-hello2',
            'name': 'testing.txt',
            'content_type': 'text/plain',
        }
    ]
    dummy_server.app['s3_emails']['s3-test-path'] = msg.as_string()

    r = await cli.get(
        factory.url('ui:get-file', conv=conv_key, action_id=3, content_id='testing-hello2'), allow_redirects=False
    )
    assert r.status == 307, await r.text()
    assert r.headers['Location'].startswith(
        f'https://s3_temp_bucket.example.com/{conv_key}/s3-test-path/testing-hello2/testing.txt?'
        f'AWSAccessKeyId=testing_access_key&Signature='
    )
    assert dummy_server.log == [
        'GET s3_endpoint_url/foobar/s3-test-path',
        f'PUT s3_endpoint_url/s3_temp_bucket.example.com/{conv_key}/s3-test-path/testing-hello2/testing.txt',
    ]


async def test_get_file_ongoing(settings, db_conn, redis):
    c = CopyToTemp(settings, db_conn, redis)
    assert await c._await_ongoing('foo') == 0

    await redis.set('get-files:123', 1)
    with pytest.raises(HTTPGatewayTimeout):
        await c._await_ongoing('get-files:123', sleep=0)

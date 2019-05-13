import json

import pytest
from aiohttp.web_exceptions import HTTPGatewayTimeout
from arq.jobs import Job
from pytest_toolbox.comparison import RegexStr

from em2.background import push_all
from em2.core import conv_actions_json, get_flag_counts
from em2.protocol.views.fallback_utils import process_smtp
from em2.utils.smtp import CopyToTemp, File, find_smtp_files

from .conftest import Factory


async def test_clean_email(fake_request, db_conn, create_email, send_to_remote):
    send_id, message_id = send_to_remote

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    msg = create_email(
        html_body="""
        outside body
        <body>
          <style>body {color: red}</style>
          <div dir="ltr">this is a reply<br clear="all"/>
          <div class="gmail_signature">this is a signature</div>
          <div class="gmail_quote">
            <div class="gmail_attr" dir="ltr">On Fri, 15 Mar 2019 at 17:00, &lt;<a
                    href="mailto:testing@imber.io">testing@imber.io</a>&gt; wrote:<br/></div>
            <blockquote class="gmail_quote" style="margin:0px 0px 0px 0.8ex;padding-left:1ex">
              <p>whatever</p>
            </blockquote>
          </div>
        </body>
        """,
        headers={'In-Reply-To': message_id},
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    body = await db_conn.fetchval("select body from actions where act='message:add' order by pk desc limit 1")
    assert body == (
        'outside body\n'
        '        <body>\n'
        '<style>body {color: red}</style>\n'
        '<div dir="ltr">this is a reply<br clear="all"/>\n'
        '<div class="gmail_signature">this is a signature</div>\n'
        '</div></body>'
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


async def test_attachment_actions(fake_request, factory: Factory, db_conn, redis, create_email, attachment):
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
            'actor': 'sender@remote.com',
            'participant': 'sender@remote.com',
        },
        {
            'id': 2,
            'conv': RegexStr('.*'),
            'act': 'participant:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@remote.com',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 3,
            'conv': RegexStr('.*'),
            'act': 'message:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@remote.com',
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
            'actor': 'sender@remote.com',
            'body': 'Test Subject',
        },
    ]
    assert len(await redis.keys('arq:job:*')) == 0
    await push_all(db_conn, redis, conv_id, transmit=True)
    arq_keys = await redis.keys('arq:job:*')
    assert len(arq_keys) == 1
    key = arq_keys[0].replace('arq:job:', '')
    job = Job(key, redis)
    job_info = await job.info()
    ws_data = json.loads(job_info.args[0])
    assert ws_data['actions'] == data


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

    url = factory.url('ui:get-file', conv=conv_key, content_id='testing-hello2')
    r1 = await cli.get(url, allow_redirects=False)
    assert r1.status == 302, await r1.text()
    assert r1.headers['Location'].startswith(
        f'https://s3_temp_bucket.example.com/{conv_key}/s3-test-path/testing-hello2/testing.txt?'
        f'AWSAccessKeyId=testing_access_key&Signature='
    )

    r2 = await cli.get(url, allow_redirects=False)
    assert r2.status == 302, await r2.text()
    assert r2.headers['Location'] == r1.headers['Location']

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


def test_finding_attachment(create_email, attachment, create_image):
    image_data = create_image()
    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[
            attachment('testing.tff', 'font/ttf', b'foobar'),
            attachment('testing.txt', 'text/plain', 'hello', {'Content-ID': 'testing-hello2'}),
            attachment(
                'testing.jpeg', 'image/jpeg', image_data, {'Content-ID': 'foobar-123', 'Content-Disposition': 'inline'}
            ),
        ],
    )
    attachments = list(find_smtp_files(msg, True))
    assert attachments == [
        File(
            hash='816f0241b8a5f206b224197b87b2cbc464e626a9',
            name='testing.tff',
            content_id='816f0241b8a5f206b224197b87b2cbc464e626a9',
            content_disp='attachment',
            content_type='font/ttf',
            content=b'foobar',
        ),
        File(
            hash='874f36549f57ff5d6596dd153cb94524f1eeebc1',
            name='testing.txt',
            content_id='testing-hello2',
            content_disp='attachment',
            content_type='text/plain',
            content=b'hello\n',
        ),
        File(
            hash='fc0f9baebcd2abc35d49151df755603d1c52fe4b',
            name=None,
            content_id='foobar-123',
            content_disp='inline',
            content_type='image/jpeg',
            content=image_data,
        ),
    ]


async def test_spam(fake_request, db_conn, create_email, factory: Factory, cli, redis):
    user = await factory.create_user()

    counts = await get_flag_counts(user.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    msg = create_email(html_body='this is spam')
    await process_smtp(fake_request, msg, {user.email}, 's3://foobar/whatever', spam=True, warnings={'testing': 'xxx'})

    assert True is await db_conn.fetchval('select spam from participants where user_id = $1', user.id)
    assert None is await db_conn.fetchval('select spam from participants where user_id != $1', user.id)

    counts = await get_flag_counts(user.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}

    r = await cli.get(factory.url('ui:get', conv=await db_conn.fetchval('select key from conversations')))
    assert r.status == 200, await r.text()
    obj = await r.json()
    assert obj[2]['body'] == 'this is spam'
    assert obj[2]['warnings'] == {'testing': 'xxx'}


async def test_spam_existing_conv(fake_request, db_conn, create_email, send_to_remote, factory: Factory, redis):
    send_id, message_id = send_to_remote

    u1 = factory.user
    counts = await get_flag_counts(u1.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    assert 2 == await db_conn.fetchval('select count(*) from users')
    u2_id = await db_conn.fetchval('select id from users where id != $1', u1.id)

    u3 = await factory.create_user()
    counts = await get_flag_counts(u3.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    msg = create_email(html_body='reply', headers={'In-Reply-To': message_id})
    await process_smtp(fake_request, msg, {u1.email, u3.email}, 's3://foobar/whatever', spam=True, warnings={'w': 'x'})

    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")

    new_msg = await db_conn.fetchval("select pk from actions where act='message:add' order by pk desc limit 1")
    assert 'reply' == await db_conn.fetchval('select body from actions where pk=$1', new_msg)
    warnings = await db_conn.fetchval('select warnings from actions where pk=$1', new_msg)
    assert json.loads(warnings) == {'w': 'x'}

    assert None is await db_conn.fetchval('select spam from participants where user_id = $1', u1.id)
    assert None is await db_conn.fetchval('select spam from participants where user_id = $1', u2_id)
    assert True is await db_conn.fetchval('select spam from participants where user_id = $1', u3.id)

    counts = await get_flag_counts(u1.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    counts = await get_flag_counts(u3.id, conn=db_conn, redis=redis)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}

import json
from email.message import EmailMessage

import pytest
from aiohttp.web_exceptions import HTTPGatewayTimeout
from arq.jobs import Job
from pytest_toolbox.comparison import RegexStr

from em2.background import push_all
from em2.core import File, conv_actions_json, get_flag_counts
from em2.protocol.views.smtp_utils import InvalidEmailMsg, process_smtp
from em2.utils.smtp import CopyToTemp, find_smtp_files

from .conftest import Factory


async def test_clean_email(conns, db_conn, create_email, send_to_remote):
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
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
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


async def test_attachment_content_id(conns, factory: Factory, db_conn, create_email, attachment, create_image):
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
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
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
        'hash': 'f1684d46ae5b40a4b0c7c06eb19282d0',
        'content_id': 'foobar-123',
        'name': None,
        'content_type': 'image/jpeg',
    }


async def test_attachment_actions(conns, factory: Factory, db_conn, redis, create_email, attachment):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[
            attachment('testing1.txt', 'text/plain', 'hello1'),
            attachment('testing2.txt', 'text/plain', 'hello2', {'Content-ID': 'testing-hello2'}),
        ],
    )
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
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
        'hash': 'b52731692f35498bba7e4660142129d2',
        'content_id': RegexStr('.{36}'),
        'name': 'testing1.txt',
        'content_type': 'text/plain',
    }
    conv_id, conv_key = await db_conn.fetchrow('select id, key from conversations')
    data = json.loads(await conv_actions_json(conns, factory.user.id, conv_id))
    assert data == [
        {
            'id': 1,
            'act': 'participant:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@example.net',
            'participant': 'sender@example.net',
        },
        {
            'id': 2,
            'act': 'participant:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@example.net',
            'participant': 'testing-1@example.com',
        },
        {
            'id': 3,
            'act': 'message:add',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@example.net',
            'body': 'This is the <b>message</b>.',
            'msg_format': 'html',
            'files': [
                {
                    'content_disp': 'attachment',
                    'hash': 'b52731692f35498bba7e4660142129d2',
                    'content_id': RegexStr('.{36}'),
                    'name': 'testing1.txt',
                    'content_type': 'text/plain',
                    'size': 7,
                },
                {
                    'content_disp': 'attachment',
                    'hash': 'a10edbbb8f28f8e98ee6b649ea2556f4',
                    'content_id': 'testing-hello2',
                    'name': 'testing2.txt',
                    'content_type': 'text/plain',
                    'size': 7,
                },
            ],
        },
        {
            'id': 4,
            'act': 'conv:publish',
            'ts': '2032-01-01T12:00:00+00:00',
            'actor': 'sender@example.net',
            'body': 'Test Subject',
        },
    ]
    push_data = list(data)
    push_data[-1]['extra_body'] = False
    push_data[-2]['extra_body'] = False
    assert len(await redis.keys('arq:job:*')) == 1
    await push_all(conns, conv_id, transmit=True)
    arq_keys = await redis.keys('arq:job:*')
    assert len(arq_keys) == 3
    for key in arq_keys:
        key = key.replace('arq:job:', '')
        job = Job(key, redis)
        job_info = await job.info()
        if job_info.function == 'push_actions':
            ws_data = json.loads(job_info.args[0])
            assert ws_data['actions'] == push_data


async def test_get_file(conns, factory: Factory, db_conn, create_email, attachment, cli, dummy_server):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[attachment('testing.txt', 'text/plain', 'hello', {'Content-ID': 'testing-hello2'})],
    )
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/s3-test-path')

    assert 1 == await db_conn.fetchval("select count(*) from files")

    conv_key = await db_conn.fetchval('select key from conversations')
    data = json.loads(await conv_actions_json(conns, factory.user.id, conv_key))
    assert data[2]['files'] == [
        {
            'content_disp': 'attachment',
            'hash': 'b1946ac92492d2347c6235b4d2611184',
            'content_id': 'testing-hello2',
            'name': 'testing.txt',
            'content_type': 'text/plain',
            'size': 6,
        }
    ]
    dummy_server.app['s3_files']['s3-test-path'] = msg.as_string()

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
        'GET /s3_endpoint_url/foobar/s3-test-path > 200',
        f'PUT /s3_endpoint_url/s3_temp_bucket.example.com/{conv_key}/s3-test-path/testing-hello2/testing.txt > 200',
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
            hash='3858f62230ac3c915f300c664312c63f',
            name='testing.tff',
            content_id=RegexStr('.{36}'),
            content_disp='attachment',
            content_type='font/ttf',
            size=6,
            content=b'foobar',
        ),
        File(
            hash='b1946ac92492d2347c6235b4d2611184',
            name='testing.txt',
            content_id='testing-hello2',
            content_disp='attachment',
            content_type='text/plain',
            size=6,
            content=b'hello\n',
        ),
        File(
            hash='f1684d46ae5b40a4b0c7c06eb19282d0',
            name=None,
            content_id='foobar-123',
            content_disp='inline',
            content_type='image/jpeg',
            size=len(image_data),
            content=image_data,
        ),
    ]


async def test_spam(conns, db_conn, create_email, factory: Factory, cli):
    user = await factory.create_user()

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    msg = create_email(html_body='this is spam')
    await process_smtp(conns, msg, {user.email}, 's3://foobar/whatever', spam=True, warnings={'testing': 'xxx'})

    assert True is await db_conn.fetchval('select spam from participants where user_id = $1', user.id)
    assert None is await db_conn.fetchval('select spam from participants where user_id != $1', user.id)

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}

    obj = await cli.get_json(
        factory.url('ui:get-actions', conv=await db_conn.fetchval('select key from conversations'))
    )
    assert obj[2]['body'] == 'this is spam'
    assert obj[2]['warnings'] == {'testing': 'xxx'}


async def test_spam_existing_conv(conns, db_conn, create_email, send_to_remote, factory: Factory):
    send_id, message_id = send_to_remote

    u1 = factory.user
    counts = await get_flag_counts(conns, u1.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    assert 2 == await db_conn.fetchval('select count(*) from users')
    u2_id = await db_conn.fetchval('select id from users where id != $1', u1.id)

    u3 = await factory.create_user()
    counts = await get_flag_counts(conns, u3.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    msg = create_email(html_body='reply', headers={'In-Reply-To': message_id})
    await process_smtp(conns, msg, {u1.email, u3.email}, 's3://foobar/whatever', spam=True, warnings={'w': 'x'})

    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")

    new_msg = await db_conn.fetchval("select pk from actions where act='message:add' order by pk desc limit 1")
    assert 'reply' == await db_conn.fetchval('select body from actions where pk=$1', new_msg)
    warnings = await db_conn.fetchval('select warnings from actions where pk=$1', new_msg)
    assert json.loads(warnings) == {'w': 'x'}

    assert None is await db_conn.fetchval('select spam from participants where user_id = $1', u1.id)
    assert None is await db_conn.fetchval('select spam from participants where user_id = $1', u2_id)
    assert True is await db_conn.fetchval('select spam from participants where user_id = $1', u3.id)

    counts = await get_flag_counts(conns, u1.id)
    assert counts == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    counts = await get_flag_counts(conns, u3.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}


async def test_reply_attachment(factory, conns, db_conn, create_email, send_to_remote, attachment):
    await factory.create_user()

    send_id, message_id = send_to_remote

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    msg = create_email(
        html_body='this is a reply',
        headers={'In-Reply-To': message_id},
        attachments=[attachment('testing.txt', 'text/plain', 'hello', {'Content-ID': 'foobar'})],
    )
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
    data = json.loads(await conv_actions_json(conns, factory.user.id, factory.conv.key))
    assert data[-1] == {
        'id': 5,
        'act': 'message:add',
        'ts': '2032-01-01T12:00:00+00:00',
        'actor': 'sender@example.net',
        'body': 'this is a reply',
        'msg_format': 'html',
        'files': [
            {
                'content_disp': 'attachment',
                'hash': 'b1946ac92492d2347c6235b4d2611184',
                'content_id': 'foobar',
                'name': 'testing.txt',
                'content_type': 'text/plain',
                'size': 6,
            }
        ],
    }


async def test_invalid_email_from(conns):
    msg = EmailMessage()
    msg['To'] = 'testing@example.com'
    msg.set_content('testing')

    with pytest.raises(InvalidEmailMsg) as exc_info:
        await process_smtp(conns, msg, {'testing@example.com'}, 's3://foobar/whatever')
    assert exc_info.value.args[0] == 'invalid "From" header'


async def test_invalid_email_msg_id(conns):
    msg = EmailMessage()
    msg['From'] = 'other@example.net'
    msg['To'] = 'testing@example.com'
    msg.set_content('testing')

    with pytest.raises(InvalidEmailMsg) as exc_info:
        await process_smtp(conns, msg, {'testing@example.com'}, 's3://foobar/whatever')
    assert exc_info.value.args[0] == 'no "Message-ID" header found'


async def test_invalid_email_no_date(conns):
    msg = EmailMessage()
    msg['From'] = 'other@example.net'
    msg['To'] = 'testing@example.com'
    msg['Message-ID'] = 'testing@example.net'
    # msg['Date'] = 'Thu, 01 Jan 2032 12:00:00 -0000'
    msg.set_content('testing')

    with pytest.raises(InvalidEmailMsg) as exc_info:
        await process_smtp(conns, msg, {'testing@example.com'}, 's3://foobar/whatever')
    assert exc_info.value.args[0] == 'invalid "Date" header'


async def test_image_extraction(conns, db_conn, create_email, send_to_remote, worker, dummy_server):
    send_id, message_id = send_to_remote

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    url1 = dummy_server.server_name + '/image/?size=123'
    url2 = dummy_server.server_name + '/image/?size=456'
    msg = create_email(
        html_body=f"""
        <style>body {{background: url("{url1}")}}</style>
        <body>
          <p>This is the body.</p>
          <img src="{url2}" alt="Testing" height="42" width="42">
          <img src="cid:foobar" alt="embedded attachment">
        </body>
        """,
        headers={'In-Reply-To': message_id},
    )
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    body = await db_conn.fetchval("select body from actions where act='message:add' order by pk desc limit 1")
    assert body == (
        f'<style>body {{background: url("{url1}")}}</style>\n'
        f'<body>\n'
        f'<p>This is the body.</p>\n'
        f'<img alt="Testing" height="42" src="{url2}" width="42"/>\n'
        f'<img alt="embedded attachment" src="cid:foobar"/>\n'
        f'</body>'
    )
    assert await db_conn.fetchval("select details->>'prev' from conversations") == 'This is the body.'

    assert await worker.run_check() == 5
    assert len(dummy_server.log) == 4
    assert {dummy_server.log[0], dummy_server.log[1]} == {'GET /image/?size=456 > 200', 'GET /image/?size=123 > 200'}
    assert dummy_server.log[2].startswith('PUT /s3_endpoint_url/s3_cache_bucket.example.com/')
    assert dummy_server.log[3].startswith('PUT /s3_endpoint_url/s3_cache_bucket.example.com/')

    cache_files = await db_conn.fetch('select url, error, size, hash, content_type from image_cache order by size')
    assert [dict(r) for r in cache_files] == [
        {
            'url': url1,
            'error': None,
            'size': 123,
            'hash': '9ed9bf64e48c7b343c6dd5700c3ae57fb517a01bac891fd19c1dab57b23accdc',
            'content_type': 'image/png',
        },
        {
            'url': url2,
            'error': None,
            'size': 456,
            'hash': '2cd3827451fd0fdf29d52743e49930d28228275cb960a25f3a973fe827389e7f',
            'content_type': 'image/png',
        },
    ]


async def test_image_extraction_many(conns, db_conn, create_email, send_to_remote, worker, dummy_server):
    send_id, message_id = send_to_remote

    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")

    msg = create_email(
        html_body='\n'.join(
            f"<img src='{dummy_server.server_name}/image/?size={i}'/>"
            for i in range(15)  # more than the limit 10 as per conftest
        ),
        headers={'In-Reply-To': message_id},
    )
    await process_smtp(conns, msg, ['testing-1@example.com'], 's3://foobar/whatever')
    assert 2 == await db_conn.fetchval("select count(*) from actions where act='message:add'")

    assert await worker.run_check() == 5
    assert len(dummy_server.log) == 20

    assert await db_conn.fetchval('select count(*) from image_cache') == 10


async def test_send_to_many(conns, factory: Factory, db_conn, create_email, create_image):
    await factory.create_user()

    recipients = ['b@ex.com', 'testing-1@example.com', 'a@ex.com', 'd@ex.com', 'c@ex.com']
    msg = create_email(html_body='This is the <b>message</b>.', to=recipients)
    await process_smtp(conns, msg, recipients, 's3://foobar/whatever')
    v = await db_conn.fetch('select email from participants p join users u on p.user_id = u.id order by p.id')
    prt_addrs = [r[0] for r in v]
    assert prt_addrs == ['sender@example.net'] + recipients

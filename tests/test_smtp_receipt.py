import json

from pytest_toolbox.comparison import RegexStr

from em2.core import conv_actions_json
from em2.protocol.views.fallback_utils import process_smtp

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
        attachments=[attachment('testing.jpeg', 'image/jpeg', create_image(), {'Content-ID': 'foobar-123'})],
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    assert 'This is the <b>message</b>.' == await db_conn.fetchval("select body from actions where act='message:add'")

    assert 1 == await db_conn.fetchval("select count(*) from files")
    file = await db_conn.fetchrow('select action, storage, type, ref, name, content_type from files')
    assert dict(file) == {
        'action': await db_conn.fetchval("select pk from actions where act='message:add'"),
        'storage': None,
        'type': 'attachment',
        'ref': 'foobar-123',
        'name': 'testing.jpeg',
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
        select action, storage, type, ref, name, content_type
        from files
        where name='testing1.txt'
        """
    )
    assert dict(file) == {
        'action': await db_conn.fetchval("select pk from actions where act='message:add'"),
        'storage': None,
        'type': 'attachment',
        'ref': '578b46f8e0a475175f9219db37fe4bd1',
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
                {'type': 'attachment', 'name': 'testing2.txt', 'ref': 'testing-hello2', 'content_type': 'text/plain'},
                {
                    'type': 'attachment',
                    'name': 'testing1.txt',
                    'ref': '578b46f8e0a475175f9219db37fe4bd1',
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

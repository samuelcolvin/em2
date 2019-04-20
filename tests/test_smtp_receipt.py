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


async def test_attachment(fake_request, factory: Factory, db_conn, create_email, create_image):
    await factory.create_user()

    msg = create_email(
        html_body='This is the <b>message</b>.',
        attachments=[('testing.jpeg', 'image/jpeg', create_image(), {'Content-ID': 'foobar-123'})],
    )
    await process_smtp(fake_request, msg, {'testing-1@example.com'}, 's3://foobar/whatever')
    assert 1 == await db_conn.fetchval("select count(*) from actions where act='message:add'")
    assert 'This is the <b>message</b>.' == await db_conn.fetchval("select body from actions where act='message:add'")

    assert 1 == await db_conn.fetchval("select count(*) from files")
    file = await db_conn.fetchrow('select action, storage, type, ref, name, content_type from files')
    assert dict(file) == {
        'action': await db_conn.fetchval('select pk from actions order by id limit 1'),
        'storage': None,
        'type': 'attachment',
        'ref': 'foobar-123',
        'name': 'testing.jpeg',
        'content_type': 'image/jpeg',
    }

import base64

from pytest_toolbox.comparison import AnyInt, CloseToNow, RegexStr

from em2.core import ActionModel, ActionTypes
from em2.protocol.smtp.images import get_images
from em2.ui.views.files import delete_stale_upload

from .conftest import Factory


async def test_get_file_link(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:upload-file', conv=conv.key, query=q))
    content_id = obj['content_id']
    assert obj == {
        'content_id': RegexStr('.{36}'),
        'url': 'https://s3_files_bucket.example.com/',
        'fields': {
            'Key': f'{conv.key}/{content_id}/testing.png',
            'Content-Type': 'image/jpeg',
            'AWSAccessKeyId': 'testing_access_key',
            'Content-Disposition': 'attachment; filename="testing.png"',
            'Policy': RegexStr('.*'),
            'Signature': RegexStr('.*'),
        },
    }


async def test_get_file_link_invalid_ct(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    q = dict(filename='testing.png', content_type='foobar', size='123456')
    obj = await cli.get_json(factory.url('ui:upload-file', conv=conv.key, query=q), status=400)
    assert obj == {
        'message': 'Invalid query data',
        'details': [{'loc': ['content_type'], 'msg': 'invalid Content-Type', 'type': 'value_error'}],
    }


async def test_get_file_link_non_creator(cli, factory: Factory):
    await factory.create_user()
    user2 = await factory.create_user()
    conv = await factory.create_conv(publish=True, participants=[{'email': user2.email}])

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:upload-file', conv=conv.key, query=q, session_id=user2.session_id))
    assert obj['url'] == 'https://s3_files_bucket.example.com/'


async def test_get_file_link_not_permitted(cli, factory: Factory):
    user = await factory.create_user()
    user2 = await factory.create_user()
    conv = await factory.create_conv(publish=True, participants=[{'email': user2.email}])

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=user2.email, follows=1))

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    url = factory.url('ui:upload-file', conv=conv.key, query=q, session_id=user2.session_id)
    obj = await cli.get_json(url, status=403)
    assert obj == {'message': 'file attachment not permitted'}


async def test_delete_stale_upload(settings, db_conn, dummy_server):
    ctx = {'settings': settings, 'pg': db_conn}
    assert await delete_stale_upload(ctx, 0, 'foobar', 's3://testing.example.com/123/foobar/whatever.png') == 1
    assert len(dummy_server.log) == 1


async def test_delete_stale_upload_file_exists(settings, db_conn, factory: Factory, dummy_server):
    await factory.create_user()
    conv = await factory.create_conv()
    await db_conn.execute(
        """
        insert into files (conv, action, content_disp, hash, content_id)
        values ($1, $2, 'attachment', '123', 'foobar')
        """,
        conv.id,
        await db_conn.fetchval("select pk from actions where act='message:add'"),
    )

    ctx = {'settings': settings, 'pg': db_conn}
    assert await delete_stale_upload(ctx, conv.id, 'foobar', 's3://testing.example.com/123/foobar/whatever.png') is None
    assert len(dummy_server.log) == 0


async def test_message_with_attachment(cli, factory: Factory, db_conn, dummy_server):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    q = dict(filename='testing.png', content_type='image/jpeg', size='14')
    obj = await cli.get_json(factory.url('ui:upload-file', conv=conv.key, query=q))
    content_id = obj['content_id']

    dummy_server.app['s3_files'][f'{conv.key}/{content_id}/testing.png'] = 'this is a test'

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}], 'files': [content_id]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)

    data = await db_conn.fetchrow('select * from files')
    assert dict(data) == {
        'id': AnyInt(),
        'conv': conv.id,
        'action': AnyInt(),
        'send': None,
        'storage': RegexStr('s3://s3_files_bucket.example.com/.*'),
        'storage_expires': None,
        'content_disp': 'inline',
        'hash': 'foobar',
        'content_id': content_id,
        'name': 'testing.png',
        'content_type': 'text/plain; charset=utf-8',
        'size': 14,
    }


async def test_message_with_attachment_no_file(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}], 'files': ['foobar']}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data, status=400)
    assert await r.json() == {'message': "no file found for content id 'foobar'"}


async def test_message_with_attachment_not_uploaded(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    q = dict(filename='testing.png', content_type='image/jpeg', size='14')
    obj = await cli.get_json(factory.url('ui:upload-file', conv=conv.key, query=q))
    content_id = obj['content_id']

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}], 'files': [content_id]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data, status=400)
    assert await r.json() == {'message': 'file not uploaded'}


async def test_get_images_ok(worker_ctx, factory: Factory, dummy_server, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    action = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    url = dummy_server.server_name + '/image/'
    await get_images(worker_ctx, conv.id, action, {url})

    assert len(dummy_server.log) == 2
    assert dummy_server.log[0] == 'GET image'
    assert await db_conn.fetchval('select count(*) from image_cache') == 1
    r = dict(await db_conn.fetchrow('select * from image_cache'))
    assert r == {
        'id': AnyInt(),
        'action': action,
        'conv': conv.id,
        'storage': RegexStr(f's3://s3_cache_bucket.example.com/{conv.key}/.+?.png'),
        'error': None,
        'created': CloseToNow(),
        'last_access': None,
        'url': url,
        'hash': '5b09369749b5240d619e70883c4c89030708917c1b2f5f81e2dc1094c451fff9',
        'size': 10,
        'content_type': 'image/png',
    }


async def test_get_images_bad(worker_ctx, factory: Factory, dummy_server, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    action = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    await get_images(
        worker_ctx,
        conv.id,
        action,
        {
            dummy_server.server_name + '/status/200/',  # wrong content_type
            dummy_server.server_name + '/status/201/',  # wrong status
            dummy_server.server_name + '/image/?size=700',  # too large
            'this-is-not-a-valid-url.com/broken',
        },
    )

    assert len(dummy_server.log) == 3
    # assert dummy_server.log[0] == 'GET image'
    assert await db_conn.fetchval('select count(*) from image_cache') == 4
    cache_files = await db_conn.fetch(
        'select url, storage, error, size, hash, content_type from image_cache order by error'
    )
    assert [dict(r) for r in cache_files] == [
        {
            'url': dummy_server.server_name + '/status/201/',
            'storage': None,
            'error': 201,
            'size': None,
            'hash': None,
            'content_type': None,
        },
        {
            'url': dummy_server.server_name + '/image/?size=700',
            'storage': None,
            'error': 1413,
            'size': None,
            'hash': None,
            'content_type': None,
        },
        {
            'url': dummy_server.server_name + '/status/200/',
            'storage': None,
            'error': 1415,
            'size': None,
            'hash': None,
            'content_type': None,
        },
        {
            'url': 'this-is-not-a-valid-url.com/broken',
            'storage': None,
            'error': 1502,
            'size': None,
            'hash': None,
            'content_type': None,
        },
    ]


async def test_get_images_exist_on_conv(worker_ctx, factory: Factory, dummy_server, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    action = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    url = dummy_server.server_name + '/image/'
    await get_images(worker_ctx, conv.id, action, {url})
    assert len(dummy_server.log) == 2

    await get_images(worker_ctx, conv.id, action, {url})
    assert len(dummy_server.log) == 2
    assert await db_conn.fetchval('select count(*) from image_cache') == 1


async def test_get_images_exist_elsewhere(worker_ctx, factory: Factory, dummy_server, db_conn):
    await factory.create_user()
    conv1 = await factory.create_conv()
    action1 = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    url = dummy_server.server_name + '/image/'
    await get_images(worker_ctx, conv1.id, action1, {url})
    assert len(dummy_server.log) == 2

    conv2 = await factory.create_conv()
    action2 = await db_conn.fetchval('select pk from actions order by id desc limit 1')
    await get_images(worker_ctx, conv2.id, action2, {url})
    assert len(dummy_server.log) == 3  # got the image again, matching hash
    assert await db_conn.fetchval('select count(*) from image_cache') == 2
    cache_files = await db_conn.fetch('select url, conv, error, size, hash from image_cache order by conv')

    assert [dict(r) for r in cache_files] == [
        {
            'url': url,
            'conv': conv1.id,
            'error': None,
            'size': 10,
            'hash': '5b09369749b5240d619e70883c4c89030708917c1b2f5f81e2dc1094c451fff9',
        },
        {
            'url': url,
            'conv': conv2.id,
            'error': None,
            'size': 10,
            'hash': '5b09369749b5240d619e70883c4c89030708917c1b2f5f81e2dc1094c451fff9',
        },
    ]


async def test_download_cache_image(worker_ctx, factory: Factory, dummy_server, db_conn, cli):
    await factory.create_user()
    conv = await factory.create_conv()
    action = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    url = dummy_server.server_name + '/image/'
    await get_images(worker_ctx, conv.id, action, {url})

    assert await db_conn.fetchval('select count(*) from image_cache') == 1

    url_enc = base64.b64encode(url.encode()).decode()
    r = await cli.get(factory.url('ui:get-html-image', conv=conv.key, url=url_enc), allow_redirects=False)
    assert r.status == 302, await r.text()
    assert r.headers['Location'].startswith('https://s3_cache_bucket.example.com/')


async def test_download_cache_image_bad(worker_ctx, factory: Factory, dummy_server, db_conn, cli):
    await factory.create_user()
    conv = await factory.create_conv()
    action = await db_conn.fetchval('select pk from actions order by id desc limit 1')

    url = dummy_server.server_name + '/status/502/'
    await get_images(worker_ctx, conv.id, action, {url})

    assert await db_conn.fetchval('select count(*) from image_cache') == 1

    url_enc = base64.b64encode(url.encode()).decode()
    r = await cli.get(factory.url('ui:get-html-image', conv=conv.key, url=url_enc))
    text = await r.text()
    assert r.status == 200, text
    assert text == 'unable to download image, response 502'


async def test_download_cache_image_invalid_url(factory: Factory, cli):
    await factory.create_user()
    conv = await factory.create_conv()

    obj = await cli.get_json(factory.url('ui:get-html-image', conv=conv.key, url='foobar'), status=400)
    assert obj == {'message': 'invalid url'}

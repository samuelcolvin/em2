from pytest_toolbox.comparison import AnyInt, RegexStr

from em2.core import ActionModel, ActionTypes
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
        'url': 'https://s3.us-east-1.amazonaws.com/s3_files_bucket.example.com',
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
    assert obj['url'] == 'https://s3.us-east-1.amazonaws.com/s3_files_bucket.example.com'


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

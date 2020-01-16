from operator import itemgetter

import pytest
from pytest_toolbox.comparison import AnyInt, RegexStr

from em2.contacts import add_contacts
from em2.core import Action, ActionTypes
from em2.ui.views.contacts import delete_stale_image
from em2.utils.images import InvalidImage, _do_resize, _resize_crop_dims

from .conftest import Factory, UserTestClient, create_image, create_raw_image


async def test_create_conv(cli: UserTestClient, factory: Factory, db_conn):
    user = await factory.create_user()

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    await cli.post_json(
        factory.url('ui:create'),
        {'subject': 'Sub', 'message': 'Msg', 'participants': [{'email': 'foobar@example.com'}]},
        status=201,
    )

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    owner, profile_user = await db_conn.fetchrow('select owner, profile_user from contacts order by id desc')
    assert owner == user.id
    assert profile_user == await db_conn.fetchval('select id from users where email=$1', 'foobar@example.com')


async def test_act_add_contact(cli: UserTestClient, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    data = {'actions': [{'act': 'participant:add', 'participant': 'new@example.com'}]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    owner, profile_user = await db_conn.fetchrow('select owner, profile_user from contacts order by id desc')
    assert owner == user.id
    assert profile_user == await db_conn.fetchval('select id from users where email=$1', 'new@example.com')


async def test_add_contacts(factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)
    assert await db_conn.fetchval('select count(*) from contacts') == 1
    await add_contacts(conns, conv.id, user.id)
    await add_contacts(conns, conv.id, user.id)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    owner, profile_user, profile_type = await db_conn.fetchrow(
        'select owner, profile_user, profile_type from contacts order by id desc'
    )
    assert owner == user.id
    assert profile_user == await db_conn.fetchval('select id from users where email=$1', 'new@example.com')
    assert profile_type is None


async def test_lookup_contact(factory: Factory, cli: UserTestClient):
    await factory.create_user()

    await factory.create_simple_user(email='other@example.com', visibility='public', last_name='Doe')

    lines = await cli.get_ndjson(factory.url('ui:contacts-search'), params={'query': 'other@example.com'})
    assert lines == [{'email': 'other@example.com', 'is_contact': False, 'main_name': 'John', 'last_name': 'Doe'}]


async def test_lookup_contact_multiple(factory: Factory, cli: UserTestClient):
    await factory.create_user()

    await factory.create_simple_user(visibility='public-searchable', last_name='Smith')
    await factory.create_simple_user(visibility='public-searchable', main_name='Smith')

    lines = await cli.get_ndjson(factory.url('ui:contacts-search'), params={'query': 'Smith'})
    assert sorted(lines, key=itemgetter('email')) == [
        {'email': 'testing-2@example.com', 'is_contact': False, 'main_name': 'John', 'last_name': 'Smith'},
        {'email': 'testing-3@example.com', 'is_contact': False, 'main_name': 'Smith'},
    ]


async def test_lookup_contact_is_contact(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()

    other_user_id = await factory.create_simple_user(email='other@example.com', last_name='Doe')

    lines = await cli.get_ndjson(factory.url('ui:contacts-search'), params={'query': 'other@example.com'})
    assert lines == []

    await db_conn.execute(
        'insert into contacts (owner, profile_user, last_name) values ($1, $2, $3)', user.id, other_user_id, 'different'
    )

    lines = await cli.get_ndjson(factory.url('ui:contacts-search'), params={'query': 'other@example.com'})
    assert lines == [{'email': 'other@example.com', 'is_contact': True, 'main_name': 'John', 'last_name': 'different'}]


async def test_contact_list(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()
    user_contact_id = await db_conn.fetchval('select id from contacts')

    contact2_id = await factory.create_contact(
        owner=user.id,
        user_id=await factory.create_simple_user(email='foobar@example.org', main_name='a'),
        last_name='xx',
    )
    contact3_id = await factory.create_contact(
        owner=user.id,
        user_id=await factory.create_simple_user(email='second@example.org', main_name='b'),
        thumb_storage='s3://testing.com/whatever.png',
    )
    contacts = await cli.get_json(factory.url('ui:contacts-list'))
    assert contacts == {
        'pages': 1,
        'items': [
            {'id': user_contact_id, 'email': 'testing-1@example.com'},
            {'id': contact2_id, 'email': 'foobar@example.org', 'main_name': 'a', 'last_name': 'xx'},
            {
                'id': contact3_id,
                'email': 'second@example.org',
                'main_name': 'b',
                'image_url': RegexStr(r'https://testing.com/whatever\.png\?AWSAccessKeyId=testing_access_key.*'),
            },
        ],
    }


async def test_contact_details(factory: Factory, cli: UserTestClient):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org', main_name='a')
    contact_id = await factory.create_contact(
        owner=user.id, user_id=contact_user_id, last_name='xx', image_storage='s3://testing.com/whatever.png'
    )
    contact = await cli.get_json(factory.url('ui:contacts-details', id=contact_id))
    assert contact == {
        'id': contact_id,
        'user_id': contact_user_id,
        'email': 'foobar@example.org',
        'c_last_name': 'xx',
        'p_main_name': 'a',
        'c_image_url': RegexStr(r'https://testing.com/whatever\.png\?AWSAccessKeyId=testing_access_key.*'),
    }


async def test_create_contact(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    data = dict(email='foobar@example.org', main_name='Frank', last_name='Skinner')
    r = await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    assert await db_conn.fetchval('select count(*) from contacts') == 2
    c = dict(await db_conn.fetchrow('select * from contacts order by id desc'))
    assert await r.json() == {'id': c['id']}

    assert c['owner'] == user.id
    assert await db_conn.fetchval('select email from users where id=$1', c['profile_user']) == 'foobar@example.org'
    assert c['main_name'] == 'Frank'
    assert c['last_name'] == 'Skinner'


async def test_create_contact_with_image(factory: Factory, cli: UserTestClient, db_conn, dummy_server):
    user = await factory.create_user()

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(email='foobar@example.org', image=obj['file_id'])
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)

    contact_id = await db_conn.fetchval('select id from contacts order by id desc')
    assert dict(await db_conn.fetchrow('select * from contacts where id=$1', contact_id)) == {
        'id': contact_id,
        'owner': user.id,
        'profile_user': AnyInt(),
        'profile_type': 'personal',
        'main_name': None,
        'last_name': None,
        'strap_line': None,
        'image_storage': f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/main.jpg',
        'thumb_storage': f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/thumb.jpg',
        'details': None,
        'vector': None,
        'v': 1,
    }


async def test_create_contact_missing_image(factory: Factory, cli: UserTestClient):
    await factory.create_user()

    data = dict(email='foobar@example.org', image='2a84b4c7-caaa-4f6f-8570-b75d1811f978')
    r = await cli.post_json(factory.url('ui:contacts-create'), data=data, status=400)
    assert await r.json() == {'message': 'image not found', 'details': [{'loc': ['image'], 'msg': 'image not found'}]}


async def test_create_contact_invalid_image(factory: Factory, cli: UserTestClient, dummy_server):
    await factory.create_user()

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    dummy_server.app['s3_files'][obj['fields']['Key']] = b'xx'

    data = dict(email='foobar@example.org', image=obj['file_id'])
    r = await cli.post_json(factory.url('ui:contacts-create'), data=data, status=400)
    assert await r.json() == {'message': 'invalid image', 'details': [{'loc': ['image'], 'msg': 'invalid image'}]}


async def test_create_duplicate_contact(factory: Factory, cli: UserTestClient, db_conn):
    await factory.create_user()

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    data = dict(email='foobar@example.org', main_name='Frank')
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    assert await db_conn.fetchval('select count(*) from contacts') == 2
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=409)
    assert await db_conn.fetchval('select count(*) from contacts') == 2


async def test_create_contact_existing_user(factory: Factory, cli: UserTestClient, db_conn):
    await factory.create_user()

    con_user_id = await factory.create_simple_user(email='foobar@example.org', main_name='a')
    assert await db_conn.fetchval('select count(*) from contacts') == 1
    data = dict(email='foobar@example.org', main_name='Frank')
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    assert await db_conn.fetchval('select count(*) from contacts') == 2
    assert await db_conn.fetchval('select profile_user from contacts order by id desc') == con_user_id


async def test_create_org_contact(factory: Factory, cli: UserTestClient, db_conn):
    await factory.create_user()

    data = dict(email='foobar@example.org', profile_type='organisation', main_name='Frank', last_name='xxx')
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    c = await db_conn.fetchrow('select * from contacts order by id desc')
    assert c['profile_type'] == 'organisation'
    assert c['main_name'] == 'Frank'
    assert c['last_name'] is None


async def test_create_contact_not_logged_in(factory: Factory, cli: UserTestClient):
    await cli.post_json(factory.url('ui:contacts-create', session_id=123), data={}, status=401)


async def test_delete_stale_image(factory: Factory, cli: UserTestClient, worker_ctx):
    await factory.create_user()

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))

    assert await delete_stale_image(worker_ctx, obj['file_id']) == 1
    assert await delete_stale_image(worker_ctx, obj['file_id']) is None


def test_resize_crop_dims():
    img1 = create_raw_image(800, 400)
    assert _resize_crop_dims(img1, 200, 200) == ((400, 200), (100, 0, 300, 200))
    assert _resize_crop_dims(img1, 400, 400) == ((800, 400), (200, 0, 600, 400))

    img2 = create_raw_image(400, 800)
    assert _resize_crop_dims(img2, 200, 200) == ((200, 400), (0, 100, 200, 300))

    img3 = create_raw_image(200, 200)
    assert _resize_crop_dims(img3, 200, 200) == (None, None)


def test_do_resize():
    assert _do_resize(create_raw_image(800, 400), [(200, 200)]).size == (200, 200)
    assert _do_resize(create_raw_image(200, 200), [(200, 200)]).size == (200, 200)

    with pytest.raises(InvalidImage, match='image too small, minimum size 200 x 200'):
        _do_resize(create_raw_image(100, 300), [(200, 200)])


async def test_edit_contact(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()
    assert await db_conn.fetchval('select count(*) from contacts') == 1
    assert await db_conn.fetchval('select count(*) from users') == 1

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id, main_name='before')

    data = dict(last_name='after')
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    assert await db_conn.fetchval('select count(*) from users') == 2
    c = dict(await db_conn.fetchrow('select owner, profile_user, main_name, last_name from contacts order by id desc'))
    assert c == {'owner': user.id, 'profile_user': contact_user_id, 'main_name': 'before', 'last_name': 'after'}


async def test_edit_contact_get(factory: Factory, cli: UserTestClient, dummy_server):
    user = await factory.create_user()

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(email='foobar@example.org', image=obj['file_id'], main_name='before')
    r = await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    contact_id = (await r.json())['id']

    r = await cli.get_json(factory.url('ui:contacts-edit', id=contact_id))
    assert r == {
        'email': 'testing-1@example.com',
        'profile_type': 'personal',
        'main_name': 'before',
        'image': RegexStr(fr'https://s3_files_bucket\.example\.com/contacts/{user.id}/{contact_id}/main\.jpg.*'),
    }


async def test_edit_contact_user(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id)
    assert await db_conn.fetchval('select count(*) from users') == 2

    data = dict(email='different@example.org')
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    assert await db_conn.fetchval('select count(*) from users') == 3
    new_user_email = await db_conn.fetchval(
        'select email from contacts c join users u on c.profile_user = u.id order by c.id desc'
    )
    assert new_user_email == 'different@example.org'


async def test_edit_contact_image(factory: Factory, cli: UserTestClient, db_conn, dummy_server):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id)

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(image=obj['file_id'])
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    image, thumb = await db_conn.fetchrow('select image_storage, thumb_storage from contacts order by id desc')
    assert image == f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/main.jpg'
    assert thumb == f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/thumb.jpg'

    assert dummy_server.log == [
        RegexStr(r'GET /s3_endpoint_url/s3_files_bucket\.example\.com/contacts/temp/.+/testing\.png > 200'),
        RegexStr(r'DELETE /s3_endpoint_url/s3_files_bucket\.example\.com/contacts/temp/.+/testing\.png > 200'),
        f'PUT /s3_endpoint_url/s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/main.jpg > 200',
        f'PUT /s3_endpoint_url/s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/thumb.jpg > 200',
    ]


async def test_edit_contact_remove_image(factory: Factory, cli: UserTestClient, db_conn, dummy_server):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id)

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(image=obj['file_id'])
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 2
    image, thumb, v = await db_conn.fetchrow('select image_storage, thumb_storage, v from contacts order by id desc')
    assert image == f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/main.jpg'
    assert thumb == f's3://s3_files_bucket.example.com/contacts/{user.id}/{contact_id}/thumb.jpg'
    assert v == 2

    data = dict(image=None)
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)
    image, thumb, v = await db_conn.fetchrow('select image_storage, thumb_storage, v from contacts order by id desc')
    assert image is None
    assert thumb is None
    assert v == 3


async def test_edit_contact_empty(factory: Factory, cli: UserTestClient):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id)

    r = await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data={}, status=400)
    assert await r.json() == {'message': 'no data provided'}


async def test_edit_contact_wrong_owner(factory: Factory, cli: UserTestClient):
    await factory.create_user()
    user2 = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user2.id, user_id=contact_user_id)

    data = dict(last_name='foobar')
    r = await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data, status=404)
    assert await r.json() == {'message': 'contact not found'}


async def test_edit_contact_self(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user(last_name='before')
    contact_id = await db_conn.fetchval('select id from contacts')

    await db_conn.execute('update users set last_name=$1', 'before')

    data = dict(last_name='after')
    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    assert await db_conn.fetchval('select count(*) from users') == 1
    c = dict(await db_conn.fetchrow('select owner, profile_user, main_name, last_name from contacts'))
    assert c == {'owner': user.id, 'profile_user': user.id, 'main_name': None, 'last_name': None}
    u = dict(await db_conn.fetchrow('select main_name, last_name from users'))
    assert u == {'main_name': None, 'last_name': 'after'}


async def test_edit_contact_self_image(factory: Factory, cli: UserTestClient, db_conn, dummy_server):
    user = await factory.create_user(last_name='before')
    contact_id = await db_conn.fetchval('select id from contacts')

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(main_name='thing', image=obj['file_id'])

    await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data)

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    assert await db_conn.fetchval('select count(*) from users') == 1
    c = dict(await db_conn.fetchrow('select main_name, last_name, image_storage, thumb_storage from contacts'))
    assert c == {'main_name': None, 'last_name': None, 'image_storage': None, 'thumb_storage': None}
    u = dict(await db_conn.fetchrow('select main_name, last_name, image_storage, thumb_storage from users'))
    assert u == {
        'main_name': 'thing',
        'last_name': None,
        'image_storage': f's3://s3_files_bucket.example.com/users/{user.id}/main.jpg',
        'thumb_storage': f's3://s3_files_bucket.example.com/users/{user.id}/thumb.jpg',
    }


async def test_edit_contact_self_email(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user(last_name='before')
    contact_id = await db_conn.fetchval('select id from contacts')

    data = dict(last_name='after', email='different@example.org')
    r = await cli.post_json(factory.url('ui:contacts-edit', id=contact_id), data=data, status=400)
    assert await r.json() == {'message': 'you may not edit your own email address'}

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    assert await db_conn.fetchval('select count(*) from users') == 1
    c = dict(await db_conn.fetchrow('select owner, profile_user, main_name, last_name from contacts'))
    assert c == {'owner': user.id, 'profile_user': user.id, 'main_name': None, 'last_name': None}
    u = dict(await db_conn.fetchrow('select main_name, last_name from users'))
    assert u == {'main_name': None, 'last_name': None}


async def test_contact_email_lookup(factory: Factory, cli: UserTestClient):
    user = await factory.create_user()

    contact_user_id = await factory.create_simple_user(email='foobar@example.org')
    contact_id = await factory.create_contact(owner=user.id, user_id=contact_user_id, main_name='Fred', last_name='X')

    data = await cli.get_json(factory.url('ui:contacts-email-lookup'), params={'emails': 'foobar@example.org'})
    assert data == {'foobar@example.org': {'name': 'Fred X', 'contact_id': contact_id}}

    data = await cli.get_json(
        factory.url('ui:contacts-email-lookup'),
        params=[('emails', 'foobar@example.org'), ('emails', 'other@example.org')],
    )
    assert data == {'foobar@example.org': {'name': 'Fred X', 'contact_id': contact_id}}


async def test_contact_email_lookup_multiple(factory: Factory, cli: UserTestClient, db_conn):
    user = await factory.create_user()

    contact1_user_id = await factory.create_simple_user(email='anne@example.org')
    contact1_id = await factory.create_contact(owner=user.id, user_id=contact1_user_id, main_name='Anne', last_name='X')

    contact2_user_id = await factory.create_simple_user(email='ben@example.org', last_name='User', visibility='public')

    data = await cli.get_json(
        factory.url('ui:contacts-email-lookup'), params=[('emails', 'anne@example.org'), ('emails', 'ben@example.org')]
    )
    assert data == {
        'anne@example.org': {'name': 'Anne X', 'contact_id': contact1_id},
        'ben@example.org': {'name': 'John User'},
    }

    await db_conn.execute('update users set main_name=null, last_name=null where id=$1', contact2_user_id)
    data = await cli.get_json(
        factory.url('ui:contacts-email-lookup'), params=[('emails', 'anne@example.org'), ('emails', 'ben@example.org')]
    )
    assert data == {'anne@example.org': {'name': 'Anne X', 'contact_id': contact1_id}}


async def test_contact_email_lookup_contact_owner(factory: Factory, cli: UserTestClient, db_conn):
    await factory.create_user()

    other_owner = await factory.create_simple_user(email='owner@example.org')
    contact_user_id = await factory.create_simple_user(email='foobar@example.org', main_name='foobar')
    await factory.create_contact(owner=other_owner, user_id=contact_user_id, main_name='on-contact')

    data = await cli.get_json(factory.url('ui:contacts-email-lookup'), params={'emails': 'foobar@example.org'})
    assert data == {}

    await db_conn.execute("update users set visibility='public-searchable' where id=$1", contact_user_id)

    data = await cli.get_json(factory.url('ui:contacts-email-lookup'), params={'emails': 'foobar@example.org'})
    assert data == {'foobar@example.org': {'name': 'foobar'}}

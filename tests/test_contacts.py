from operator import itemgetter

from pytest_toolbox.comparison import AnyInt, RegexStr

from em2.contacts import add_contacts
from em2.core import Action, ActionTypes

from .conftest import Factory, UserTestClient, create_image


async def test_create_conv(cli: UserTestClient, factory: Factory, db_conn):
    user = await factory.create_user()

    assert await db_conn.fetchval('select count(*) from contacts') == 0
    await cli.post_json(
        factory.url('ui:create'),
        {'subject': 'Sub', 'message': 'Msg', 'participants': [{'email': 'foobar@example.com'}]},
        status=201,
    )

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    owner, profile_user = await db_conn.fetchrow('select owner, profile_user from contacts')
    assert owner == user.id
    assert profile_user == await db_conn.fetchval('select id from users where email=$1', 'foobar@example.com')


async def test_act_add_contact(cli: UserTestClient, factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval('select v from users where id=$1', user.id)

    assert await db_conn.fetchval('select count(*) from contacts') == 0
    data = {'actions': [{'act': 'participant:add', 'participant': 'new@example.com'}]}
    await cli.post_json(factory.url('ui:act', conv=conv.key), data)

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    owner, profile_user = await db_conn.fetchrow('select owner, profile_user from contacts')
    assert owner == user.id
    assert profile_user == await db_conn.fetchval('select id from users where email=$1', 'new@example.com')


async def test_add_contacts(factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)
    assert await db_conn.fetchval('select count(*) from contacts') == 0
    await add_contacts(conns, conv.id, user.id)
    await add_contacts(conns, conv.id, user.id)

    assert await db_conn.fetchval('select count(*) from contacts') == 1
    owner, profile_user, profile_type = await db_conn.fetchrow('select owner, profile_user, profile_type from contacts')
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


async def test_contact_list(factory: Factory, cli: UserTestClient):
    user = await factory.create_user()

    contact1_id = await factory.create_contact(
        owner=user.id,
        user_id=await factory.create_simple_user(email='foobar@example.org', main_name='a'),
        last_name='xx',
    )
    contact2_id = await factory.create_contact(
        owner=user.id,
        user_id=await factory.create_simple_user(email='second@example.org', main_name='b'),
        thumb_storage='s3://testing.com/whatever.png',
    )
    contacts = await cli.get_json(factory.url('ui:contacts-list'))
    assert contacts == {
        'pages': 1,
        'items': [
            {'id': contact1_id, 'email': 'foobar@example.org', 'main_name': 'a', 'last_name': 'xx'},
            {
                'id': contact2_id,
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

    assert await db_conn.fetchval('select count(*) from contacts') == 0
    data = dict(email='foobar@example.org', main_name='Frank')
    r = await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    assert await db_conn.fetchval('select count(*) from contacts') == 1
    c = dict(await db_conn.fetchrow('select * from contacts'))
    assert await r.json() == {'id': c['id']}

    assert c['owner'] == user.id
    assert await db_conn.fetchval('select email from users where id=$1', c['profile_user']) == 'foobar@example.org'
    assert c['main_name'] == 'Frank'
    assert c['last_name'] is None


async def test_create_contact_with_image(factory: Factory, cli: UserTestClient, db_conn, dummy_server):
    user = await factory.create_user()

    q = dict(filename='testing.png', content_type='image/jpeg', size='123456')
    obj = await cli.get_json(factory.url('ui:contacts-upload-image', query=q))
    path = obj['fields']['Key']
    dummy_server.app['s3_files'][path] = create_image()

    data = dict(email='foobar@example.org', image=obj['file_id'])
    await cli.post_json(factory.url('ui:contacts-create'), data=data, status=201)
    contact = dict(await db_conn.fetchrow('select * from contacts'))

    assert contact == {
        'id': AnyInt(),
        'owner': user.id,
        'profile_user': AnyInt(),
        'profile_type': 'personal',
        'main_name': None,
        'last_name': None,
        'strap_line': None,
        'image_storage': RegexStr(fr's3://s3_files_bucket.example.com/contacts/{user.id}/\d+/main.jpg'),
        'thumb_storage': RegexStr(fr's3://s3_files_bucket.example.com/contacts/{user.id}/\d+/thumb.jpg'),
        'details': None,
        'vector': None,
    }

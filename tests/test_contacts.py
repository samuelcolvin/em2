from em2.contacts import add_contacts
from em2.core import Action, ActionTypes

from .conftest import Factory, UserTestClient


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

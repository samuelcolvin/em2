import pytest
from pytest_toolbox.comparison import CloseToNow

from em2.core import ActionModel, ActionTypes

from .conftest import Factory


@pytest.fixture(name='conv')
async def _fix_conv(cli, factory: Factory, db_conn):
    await factory.create_user()
    creator = await factory.create_user()
    prts = [{'email': factory.user.email}]
    conv = await factory.create_conv(session_id=creator.session_id, publish=True, participants=prts)
    assert 2 == await db_conn.fetchval('select count(*) from participants')
    return conv


async def test_conv_set_state_inbox(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='foobar')))
    assert r.status == 400, await r.text()

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='archive')))
    assert r.status == 200, await r.text()
    assert await r.json() == {'status': 'ok'}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='archive')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not in inbox'}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='inbox')))
    assert r.status == 200, await r.text()
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='inbox')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already in inbox'}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    await db_conn.execute('update participants set inbox=false, deleted=true')

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='inbox')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'deleted or spam conversation cannot be moved to inbox'}


async def test_conv_set_state_deleted(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='delete')))
    assert r.status == 200, await r.text()
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is True
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) == CloseToNow()

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='delete')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already deleted'}
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='restore')))
    assert r.status == 200, await r.text()
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='restore')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not deleted'}
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None


async def test_conv_set_state_spam(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='spam')))
    assert r.status == 200, await r.text()
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='spam')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already spam'}
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='ham')))
    assert r.status == 200, await r.text()
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-state', conv=conv.key, query=dict(state='ham')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not spam'}
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None


async def test_conv_set_state_counts_blank(cli, factory: Factory, db_conn):
    await factory.create_user()
    r = await cli.get(factory.url('ui:conv-counts'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'states': {
            'inbox': 0,
            'inbox_unseen': 0,
            'draft': 0,
            'sent': 0,
            'archive': 0,
            'all': 0,
            'spam': 0,
            'spam_unseen': 0,
            'deleted': 0,
        },
        'labels': [],
    }


async def test_conv_set_state_counts_creator(cli, factory: Factory):
    await factory.create_user()
    await factory.create_conv()
    await factory.create_conv(publish=True)

    r = await cli.get(factory.url('ui:conv-counts'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'states': {
            'inbox': 0,
            'inbox_unseen': 0,
            'draft': 1,
            'sent': 1,
            'archive': 1,
            'all': 2,
            'spam': 0,
            'spam_unseen': 0,
            'deleted': 0,
        },
        'labels': [],
    }


async def test_conv_set_state_counts(cli, factory: Factory, db_conn):
    await factory.create_user()

    conv_inbox_unseen = await factory.create_conv(publish=True)
    conv_inbox_seen = await factory.create_conv(publish=True)
    conv_inbox_seen2 = await factory.create_conv(publish=True)
    conv_archive = await factory.create_conv(publish=True)
    conv_inbox_deleted = await factory.create_conv(publish=True)
    conv_arch_spam = await factory.create_conv(publish=True)
    conv_arch_spam_unseen = await factory.create_conv(publish=True)

    new_user = await factory.create_user()
    for r in await db_conn.fetch('select id from conversations'):
        await factory.act(factory.user.id, r[0], ActionModel(act=ActionTypes.prt_add, participant=new_user.email))

    await db_conn.execute('update participants set inbox=true, seen=null where conv=$1', conv_inbox_unseen.id)
    await db_conn.execute('update participants set inbox=true, seen=true where conv=$1', conv_inbox_seen.id)
    await db_conn.execute('update participants set inbox=true, seen=true where conv=$1', conv_inbox_seen2.id)
    await db_conn.execute('update participants set inbox=null where conv=$1', conv_archive.id)
    await db_conn.execute('update participants set deleted=true where conv=$1', conv_inbox_deleted.id)
    await db_conn.execute('update participants set inbox=null, spam=true, seen=true where conv=$1', conv_arch_spam.id)
    await db_conn.execute('update participants set spam=true, seen=null where conv=$1', conv_arch_spam_unseen.id)

    r = await cli.get(factory.url('ui:conv-counts', session_id=new_user.session_id))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'states': {
            'inbox': 3,
            'inbox_unseen': 1,
            'draft': 0,
            'sent': 0,
            'archive': 1,
            'all': 7,
            'spam': 2,
            'spam_unseen': 1,
            'deleted': 1,
        },
        'labels': [],
    }

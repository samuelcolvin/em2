from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import ActionModel, ActionTypes

from .conftest import Factory


async def test_create_conv(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(
        factory.url('ui:create'), {'subject': 'Discussion of Apples', 'message': 'I prefer red'}, status=201
    )
    obj = await r.json()
    conv_key = obj['key']

    assert 1 == await db_conn.fetchval('select count(*) from search_conv')
    search_conv = dict(await db_conn.fetchrow('select * from search_conv'))
    assert search_conv == {
        'id': AnyInt(),
        'conv_key': conv_key,
        'ts': CloseToNow(),
        'creator_email': 'testing-1@example.com',
    }
    assert 1 == await db_conn.fetchval('select count(*) from search')
    s = dict(await db_conn.fetchrow('select * from search'))
    assert s == {
        'id': AnyInt(),
        'conv': search_conv['id'],
        'user_ids': [user.id],
        'vector': "'appl':3A 'discuss':1A 'example.com':4B 'prefer':7 'red':8 'testing-1@example.com':5B",
    }


async def test_add_prt_add_msg(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from search')

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='apple **pie**'))
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from search_conv')
    assert 2 == await db_conn.fetchval('select count(*) from search')

    search_conv = dict(await db_conn.fetchrow('select * from search_conv'))
    assert search_conv == {'id': AnyInt(), 'conv_key': conv.key, 'ts': CloseToNow(), 'creator_email': user.email}

    search = await db_conn.fetch('select conv, user_ids, vector from search')
    search = [dict(r) for r in search]
    assert search == [
        {
            'conv': search_conv['id'],
            'user_ids': [user.id],
            'vector': "'example.com':3B 'messag':6 'subject':2A 'test':1A,5 'testing-1@example.com':4B",
        },
        {'conv': search_conv['id'], 'user_ids': [user.id], 'vector': "'appl':1 'pie':2"},
    ]

    user2 = await factory.create_user()
    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))
    assert 5 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from search_conv')
    assert 3 == await db_conn.fetchval('select count(*) from search')

    search = await db_conn.fetch('select conv, user_ids, vector from search')
    search = [dict(r) for r in search]
    assert search == [
        {
            'conv': search_conv['id'],
            'user_ids': [user.id, user2.id],
            'vector': "'example.com':3B 'messag':6 'subject':2A 'test':1A,5 'testing-1@example.com':4B",
        },
        {'conv': search_conv['id'], 'user_ids': [user.id, user2.id], 'vector': "'appl':1 'pie':2"},
        {
            'conv': search_conv['id'],
            'user_ids': [user.id, user2.id],
            'vector': "'example.com':2B 'testing-2@example.com':1B",
        },
    ]

import json

import pytest
from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import ActionModel, ActionTypes, File
from em2.search import search

from .conftest import Factory


async def test_create_conv(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    r = await cli.post_json(
        factory.url('ui:create'), {'subject': 'Discussion of Apples', 'message': 'I prefer red'}, status=201
    )
    obj = await r.json()
    conv_key = obj['key']
    conv_id = await db_conn.fetchval('select id from conversations where key=$1', conv_key)

    assert 1 == await db_conn.fetchval('select count(*) from search')
    s = dict(await db_conn.fetchrow('select * from search'))
    assert s == {
        'id': AnyInt(),
        'conv': conv_id,
        'action': 1,
        'freeze_action': 0,
        'ts': CloseToNow(),
        'user_ids': [user.id],
        'creator_email': user.email,
        'vector': "'appl':3A 'discuss':1A 'example.com':4B 'prefer':7 'red':8 'testing-1@example.com':5B",
    }


async def test_publish_conv(factory: Factory, cli, db_conn):
    user = await factory.create_user()
    participants = [{'email': 'anne@other.com'}, {'email': 'ben@other.com'}, {'email': 'charlie@other.com'}]
    conv = await factory.create_conv(subject='apple pie', message='eggs, flour and raisins', participants=participants)
    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert conv.id == await db_conn.fetchval('select conv from search')
    assert [user.id] == await db_conn.fetchval('select user_ids from search')

    await cli.post_json(factory.url('ui:publish', conv=conv.key), {'publish': True})

    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert conv.id == await db_conn.fetchval('select conv from search')
    user_ids = await db_conn.fetchval(
        'select array_agg(id) from (select id from users where email like $1) as t', '%@other.com'
    )
    assert len(user_ids) == 3
    assert {user.id, *user_ids} == set(await db_conn.fetchval('select user_ids from search'))


async def test_add_prt_add_msg(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from search')

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='apple **pie**'))
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from search')

    search = dict(await db_conn.fetchrow('select conv, action, user_ids, creator_email, vector from search'))
    assert search == {
        'conv': conv.id,
        'action': 4,
        'user_ids': [user.id],
        'creator_email': user.email,
        'vector': "'appl':7 'example.com':3B 'messag':6 'pie':8 'subject':2A 'test':1A,5 'testing-1@example.com':4B",
    }

    user2 = await factory.create_user()
    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))
    assert 5 == await db_conn.fetchval('select count(*) from actions')
    assert 1 == await db_conn.fetchval('select count(*) from search')

    search = dict(await db_conn.fetchrow('select conv, action, user_ids, creator_email, vector from search'))
    assert search == {
        'conv': conv.id,
        'action': 5,
        'user_ids': [user.id, user2.id],
        'creator_email': user.email,
        'vector': (
            "'appl':7 'example.com':3B,10B 'messag':6 'pie':8 'subject':2A "
            "'test':1A,5 'testing-1@example.com':4B 'testing-2@example.com':9B"
        ),
    }


async def test_add_remove_prt(factory: Factory, db_conn):
    user = await factory.create_user(email='testing@example.com')
    conv = await factory.create_conv()

    email2 = 'different@foobar.com'
    assert [4] == await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=email2))
    user2_id = await db_conn.fetchval('select id from users where email=$1', email2)
    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert 4 == await db_conn.fetchval('select action from search')
    assert [user.id, user2_id] == await db_conn.fetchval('select user_ids from search')

    email3 = 'three@foobar.com'
    assert [5] == await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=email3))
    user3_id = await db_conn.fetchval('select id from users where email=$1', email3)
    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert 5 == await db_conn.fetchval('select action from search')
    assert [user.id, user2_id, user3_id] == await db_conn.fetchval('select user_ids from search')

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=email2, follows=4))
    assert 2 == await db_conn.fetchval('select count(*) from search')
    assert 5, 5 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action!=0')
    assert [user2_id] == await db_conn.fetchval('select user_ids from search where freeze_action!=0')
    assert 5, 0 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action=0')
    assert [user.id, user3_id] == await db_conn.fetchval('select user_ids from search where freeze_action=0')

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=email3, follows=5))
    assert 2 == await db_conn.fetchval('select count(*) from search')
    assert 5, 5 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action!=0')
    assert [user2_id, user3_id] == await db_conn.fetchval('select user_ids from search where freeze_action!=0')
    assert 5, 0 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action=0')
    assert [user.id] == await db_conn.fetchval('select user_ids from search where freeze_action=0')

    assert [8] == await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='spagetti'))
    assert 2 == await db_conn.fetchval('select count(*) from search')
    assert 5, 5 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action!=0')
    assert 8, 0 == await db_conn.fetchrow('select action, freeze_action from search where freeze_action=0')

    assert 'spagetti' not in await db_conn.fetchval('select vector from search where freeze_action!=0')
    assert 'spagetti' in await db_conn.fetchval('select vector from search where freeze_action=0')


async def test_readd_prt(factory: Factory, db_conn):
    user = await factory.create_user(email='testing@example.com')
    conv = await factory.create_conv()

    email2 = 'different@foobar.com'
    assert [4] == await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=email2))
    user2_id = await db_conn.fetchval('select id from users where email=$1', email2)
    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert [user.id, user2_id] == await db_conn.fetchval('select user_ids from search where freeze_action=0')

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=email2, follows=4))
    assert 2 == await db_conn.fetchval('select count(*) from search')
    assert [user2_id] == await db_conn.fetchval('select user_ids from search where freeze_action=4')
    assert [user.id] == await db_conn.fetchval('select user_ids from search where freeze_action=0')

    assert [6] == await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=email2))
    assert 1 == await db_conn.fetchval('select count(*) from search')
    assert [user.id, user2_id] == await db_conn.fetchval('select user_ids from search where freeze_action=0')


async def test_search_query(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv(subject='apple pie', message='eggs, flour and raisins')
    assert 1 == await conns.main.fetchval('select count(*) from search')
    r = json.loads(await search(conns, user.id, 'apple'))
    assert r == {
        'conversations': [
            {
                'key': conv.key,
                'ts': CloseToNow(),
                'publish_ts': None,
                'details': {
                    'act': 'conv:create',
                    'sub': 'apple pie',
                    'email': user.email,
                    'creator': user.email,
                    'prev': 'eggs, flour and raisins',
                    'prts': 1,
                    'msgs': 1,
                },
            }
        ]
    }
    r = json.loads(await search(conns, user.id, 'banana'))
    assert r == {'conversations': []}
    assert len(json.loads(await search(conns, user.id, conv.key[5:12]))['conversations']) == 1
    assert len(json.loads(await search(conns, user.id, conv.key[5:12] + 'aaa'))['conversations']) == 0
    assert len(json.loads(await search(conns, user.id, conv.key[5:8]))['conversations']) == 0


@pytest.mark.parametrize(
    'query,count',
    [
        ('', 0),
        ('"flour and raisins"', 1),
        ('"eggs and raisins"', 0),
        ('subject:apple', 1),
        ('subject:flour', 0),
        ('from:testing@example.com', 1),
        ('from:@example.com', 1),
        ('testing@example.com', 1),
        ('includes:testing@example.com', 1),
        ('has:testing@example.com', 1),
        ('includes:@example.com', 1),
        ('to:testing@example.com', 0),
        ('to:@example.com', 0),
        ('include:recipient@foobar.com', 1),
        ('include:@foobar.com', 1),
        ('to:recipient@foobar.com', 1),
        ('to:@foobar.com', 1),
        ('recipient@foobar.com', 1),
        ('@foobar.com', 1),
        ('from:recipient@foobar.com', 0),
        ('includes:"testing@example.com recipient@foobar.com"', 1),
        ('files:*', 0),
        ('has:files', 0),
        ('rais', 1),  # prefix search
        ('rai', 1),  # prefix search
        ('ra', 0),
        ('"rais"', 0),
        ('rais!', 0),
        ('rais!', 0),
    ],
)
async def test_search_query_participants(factory: Factory, conns, query, count):
    user = await factory.create_user(email='testing@example.com')
    conv = await factory.create_conv(subject='apple pie', message='eggs, flour and raisins')
    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant='recipient@foobar.com'))

    assert len(json.loads(await search(conns, user.id, query))['conversations']) == count, repr(query)


@pytest.mark.parametrize(
    'query,count',
    [
        ('files:fat', 1),
        ('files:fat', 1),
        ('files:.png', 1),
        ('files:"cat png"', 1),
        ('files:rat', 1),
        ('files:*', 1),
        ('has:files', 1),
        ('files:apple', 0),
    ],
)
async def test_search_query_files(factory: Factory, conns, query, count):
    user = await factory.create_user(email='testing@example.com')
    conv = await factory.create_conv(subject='apple pie', message='eggs, flour and raisins')

    files = [
        File(hash='x', name='fat cat.txt', content_id='a', content_disp='inline', content_type='text/plain', size=10),
        File(hash='x', name='rat.png', content_id='b', content_disp='inline', content_type='image/png', size=100),
    ]
    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='apple **pie**'), files=files)

    assert len(json.loads(await search(conns, user.id, query))['conversations']) == count


async def test_http_search(factory: Factory, cli):
    user = await factory.create_user()
    conv = await factory.create_conv(subject='spam sandwich', message='processed meat and bread', publish=True)

    obj = await cli.get_json(factory.url('ui:search', query={'query': 'meat'}))
    assert obj == {
        'conversations': [
            {
                'key': conv.key,
                'ts': CloseToNow(),
                'publish_ts': CloseToNow(),
                'details': {
                    'act': 'conv:publish',
                    'sub': 'spam sandwich',
                    'email': user.email,
                    'creator': user.email,
                    'prev': 'processed meat and bread',
                    'prts': 1,
                    'msgs': 1,
                },
            }
        ]
    }

    obj = await cli.get_json(factory.url('ui:search'))
    assert obj == {'conversations': []}
    obj = await cli.get_json(factory.url('ui:search', query={'query': 'bacon'}))
    assert obj == {'conversations': []}

    obj = await cli.get_json(factory.url('ui:search', query={'query': 'x' * 200}))
    assert obj == {'conversations': []}


async def test_search_ranking(factory: Factory, conns):
    user = await factory.create_user()
    await factory.create_conv(subject='fish pie', message='could include apples')
    await factory.create_conv(subject='apple pie', message='eggs, flour and raisins')
    assert 2 == await conns.main.fetchval('select count(*) from search')
    results = [c['details']['sub'] for c in json.loads(await search(conns, user.id, 'apple'))['conversations']]
    assert results == ['apple pie', 'fish pie']

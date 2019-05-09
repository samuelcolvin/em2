from urllib.parse import urlencode

import pytest
from pytest_toolbox.comparison import CloseToNow

from em2.core import ActionModel, ActionTypes, get_flag_counts

from .conftest import Factory


@pytest.fixture(name='conv')
async def _fix_conv(cli, factory: Factory, db_conn):
    await factory.create_user()
    creator = await factory.create_user()
    prts = [{'email': factory.user.email}]
    conv = await factory.create_conv(session_id=creator.session_id, publish=True, participants=prts)
    assert 2 == await db_conn.fetchval('select count(*) from participants')
    return conv


async def test_conv_set_flags_inbox(cli, factory: Factory, conv, db_conn, redis):
    u_id = factory.user.id
    flags = await get_flag_counts(u_id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='foobar')))
    assert r.status == 400, await r.text()

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='archive')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': False, 'archive': True, 'deleted': False, 'spam': False},
        'counts': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 1, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='archive')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not in inbox'}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='inbox')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': True, 'archive': False, 'deleted': False, 'spam': False},
        'counts': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='inbox')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already in inbox'}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    await db_conn.execute('update participants set inbox=false, deleted=true')

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='inbox')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'deleted or spam conversation cannot be moved to inbox'}


async def test_conv_set_flags_deleted(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='delete')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': False, 'archive': False, 'deleted': True, 'spam': False},
        'counts': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 1},
    }
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is True
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) == CloseToNow()

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='delete')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already deleted'}
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='restore')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': True, 'archive': False, 'deleted': False, 'spam': False},
        'counts': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='restore')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not deleted'}
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None


async def test_conv_set_flags_spam(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='spam')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': False, 'archive': False, 'deleted': False, 'spam': True},
        'counts': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0},
    }
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='spam')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation already spam'}
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='ham')))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'conv_flags': {'inbox': True, 'archive': False, 'deleted': False, 'spam': False},
        'counts': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='ham')))
    assert r.status == 409, await r.text()
    assert await r.json() == {'message': 'conversation not spam'}
    assert await db_conn.fetchval('select spam from participants where user_id=$1', u_id) is None


async def test_conv_set_flags_sent(cli, factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv()

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='spam')))
    assert r.status == 400, await r.text()
    assert await r.json() == {'message': 'you cannot change labels on conversations you sent'}


async def test_seen(factory: Factory, conv, db_conn, redis):
    flags = await get_flag_counts(factory.user.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(factory.user.id, conv.id, ActionModel(act=ActionTypes.seen))

    flags = await get_flag_counts(factory.user.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 1, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    # already seen, shouldn't change seen count
    await factory.act(factory.user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='testing'))

    flags = await get_flag_counts(factory.user.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 1, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_conv_set_flags_counts_blank(cli, factory: Factory):
    await factory.create_user()
    r = await cli.get(factory.url('ui:conv-counts'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0},
        'labels': [],
    }


async def test_conv_set_flags_counts_creator(cli, factory: Factory):
    await factory.create_user()
    await factory.create_conv()
    await factory.create_conv(publish=True)

    r = await cli.get(factory.url('ui:conv-counts'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 1, 'archive': 0, 'all': 2, 'spam': 0, 'deleted': 0},
        'labels': [],
    }


async def test_conv_set_flags_counts(cli, factory: Factory, db_conn, redis):
    await factory.create_user()

    await factory.create_conv()
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

    await redis.delete('conv-counts*')
    r = await cli.get(factory.url('ui:conv-counts', session_id=new_user.session_id))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'flags': {'inbox': 3, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 1, 'all': 7, 'spam': 2, 'deleted': 1},
        'labels': [],
    }


def query_display(v):
    try:
        return urlencode(v)
    except TypeError:
        return ','.join(v)


@pytest.mark.parametrize(
    'query, expected',
    [
        ({}, ['anne', 'ben', 'charlie', 'dave', 'ed', 'fred', 'george']),
        ({'flag': 'inbox'}, ['charlie', 'george']),
        ({'flag': 'spam'}, ['anne']),
        ({'flag': 'archive'}, ['ben']),
        ({'flag': 'unseen'}, ['charlie']),
        ({'flag': 'deleted'}, ['dave']),
        ({'flag': 'draft'}, ['ed']),
        ({'flag': 'sent'}, ['fred']),
    ],
    ids=query_display,
)
async def test_filter_labels_conv_list(cli, factory: Factory, db_conn, query, expected):
    await factory.create_user()
    test_user = await factory.create_user()

    prts = [{'email': test_user.email}]

    conv_anne = await factory.create_conv(subject='anne', participants=prts, publish=True)
    await db_conn.execute('update participants set spam=true where conv=$1', conv_anne.id)

    conv_ben = await factory.create_conv(subject='ben', participants=prts, publish=True)
    await db_conn.execute('update participants set inbox=false where conv=$1', conv_ben.id)

    conv_charlie = await factory.create_conv(subject='charlie', participants=prts, publish=True)
    await db_conn.execute('update participants set seen=false where conv=$1', conv_charlie.id)

    conv_dave = await factory.create_conv(subject='dave', participants=prts, publish=True)
    await db_conn.execute('update participants set deleted=true where conv=$1', conv_dave.id)

    await factory.create_conv(subject='ed', session_id=test_user.session_id)
    await factory.create_conv(subject='fred', session_id=test_user.session_id, publish=True)

    conv_george = await factory.create_conv(subject='george', participants=prts, publish=True)
    await db_conn.execute('update participants set seen=true where conv=$1', conv_george.id)

    assert 7 == await db_conn.fetchval('select count(*) from conversations')
    assert 7 == await db_conn.fetchval('select count(*) from participants where user_id=$1', test_user.id)

    url = factory.url('ui:list', session_id=test_user.session_id, query=query)
    r = await cli.get(url)
    assert r.status == 200, await r.text()
    data = await r.json()
    response = [c['details']['sub'] for c in data['conversations']]
    assert response == expected, f'url: {url}, response: {response}'

    r = await cli.get(url)
    assert r.status == 200, await r.text()
    data2 = await r.json()
    assert data == data2

    if query:
        return
    # all case check results
    d = {
        c['details']['sub']: {
            'seen': c['seen'],
            'inbox': c['inbox'],
            'deleted': c['deleted'],
            'spam': c['spam'],
            'draft': c['draft'],
            'sent': c['sent'],
        }
        for c in data['conversations']
    }
    assert d == {
        'anne': {'seen': False, 'inbox': False, 'deleted': False, 'spam': True, 'draft': False, 'sent': False},
        'ben': {'seen': False, 'inbox': False, 'deleted': False, 'spam': False, 'draft': False, 'sent': False},
        'charlie': {'seen': False, 'inbox': True, 'deleted': False, 'spam': False, 'draft': False, 'sent': False},
        'dave': {'seen': False, 'inbox': False, 'deleted': True, 'spam': False, 'draft': False, 'sent': False},
        'ed': {'seen': True, 'inbox': False, 'deleted': False, 'spam': False, 'draft': True, 'sent': False},
        'fred': {'seen': True, 'inbox': False, 'deleted': False, 'spam': False, 'draft': False, 'sent': True},
        'george': {'seen': True, 'inbox': True, 'deleted': False, 'spam': False, 'draft': False, 'sent': False},
    }


async def test_draft_counts(factory: Factory, db_conn, redis):
    user = await factory.create_user()
    user2 = await factory.create_user()
    await factory.create_conv(participants=[{'email': user2.email}])

    flags = await get_flag_counts(user.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    flags = await get_flag_counts(user2.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}


async def test_published_counts(factory: Factory, db_conn, redis):
    user = await factory.create_user()
    user2 = await factory.create_user()
    await factory.create_conv(publish=True, participants=[{'email': user2.email}])

    flags = await get_flag_counts(user.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    flags = await get_flag_counts(user2.id, conn=db_conn, redis=redis)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

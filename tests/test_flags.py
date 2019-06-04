from urllib.parse import urlencode

import pytest
from pytest_toolbox.comparison import CloseToNow

from em2.core import ActionModel, ActionTypes, get_flag_counts

from .conftest import Factory


@pytest.mark.parametrize(
    'user_actions',
    [
        [
            {'conv': 'sent', 'flag': 'delete', 'change': {'sent': -1, 'deleted': 1}},
            {'conv': 'sent', 'flag': 'restore', 'change': {'sent': 1, 'deleted': -1}},
        ],
        [
            {'conv': 'draft', 'flag': 'delete', 'change': {'draft': -1, 'deleted': 1}},
            {'conv': 'draft', 'flag': 'restore', 'change': {'draft': 1, 'deleted': -1}},
        ],
        [
            {'conv': 'sent', 'flag': 'inbox', 'change': {'inbox': 1}},
            {'conv': 'sent', 'flag': 'archive', 'change': {'inbox': -1}},
        ],
        [{'conv': 'sent', 'flag': 'spam', 'status': 400, 'message': 'you cannot spam your own conversations'}],
        [{'conv': 'inbox', 'flag': 'ham', 'status': 409, 'message': 'conversation not spam'}],
        [
            {'conv': 'inbox', 'flag': 'spam', 'change': {'inbox': -1, 'spam': 1}},
            {'conv': 'inbox', 'flag': 'delete', 'change': {'deleted': 1, 'spam': -1}},
            {'conv': 'inbox', 'flag': 'restore', 'change': {'deleted': -1, 'spam': 1}},
        ],
        [
            {'conv': 'inbox_unseen', 'flag': 'delete', 'change': {'deleted': 1, 'inbox': -1, 'unseen': -1}},
            {'conv': 'inbox_unseen', 'flag': 'spam', 'change': {}},
            {'conv': 'inbox_unseen', 'flag': 'ham', 'change': {}},
        ],
        [
            {'conv': 'inbox', 'flag': 'spam', 'change': {'inbox': -1, 'spam': 1}},
            {'conv': 'inbox', 'flag': 'ham', 'change': {'inbox': 1, 'spam': -1}},
        ],
        [
            {'conv': 'inbox_unseen', 'flag': 'archive', 'change': {'archive': 1, 'inbox': -1, 'unseen': -1}},
            {'conv': 'inbox_unseen', 'flag': 'spam', 'change': {'archive': -1, 'spam': 1}},
            {'conv': 'inbox_unseen', 'flag': 'ham', 'change': {'archive': 1, 'spam': -1}},
        ],
        [
            {'conv': 'inbox_unseen', 'flag': 'archive', 'change': {'archive': 1, 'inbox': -1, 'unseen': -1}},
            {'conv': 'inbox_unseen', 'flag': 'spam', 'change': {'archive': -1, 'spam': 1}},
            {'conv': 'inbox_unseen', 'flag': 'spam', 'status': 409, 'message': 'conversation already spam'},
        ],
        [
            {'conv': 'inbox', 'flag': 'archive', 'change': {'archive': 1, 'inbox': -1}},
            {'conv': 'inbox', 'flag': 'archive', 'status': 409, 'message': 'conversation not in inbox'},
        ],
        [{'conv': 'inbox', 'flag': 'inbox', 'status': 409, 'message': 'conversation already in inbox'}],
        [{'conv': 'inbox', 'flag': 'restore', 'status': 409, 'message': 'conversation not deleted'}],
        [{'conv': 'inbox', 'flag': 'bad', 'status': 400, 'message': 'Invalid query data'}],
        [
            {'conv': 'inbox', 'flag': 'delete', 'change': {'deleted': 1, 'inbox': -1}},
            {'conv': 'inbox', 'flag': 'inbox', 'status': 400, 'message': 'deleted, spam or draft conversation cannot'},
        ],
        [
            {'conv': 'inbox', 'flag': 'delete', 'change': {'deleted': 1, 'inbox': -1}},
            {'conv': 'inbox', 'flag': 'delete', 'status': 409, 'message': 'conversation already deleted'},
        ],
        [
            {'conv': 'inbox', 'flag': 'archive', 'change': {'archive': 1, 'inbox': -1}},
            {'conv': 'inbox', 'flag': 'delete', 'change': {'archive': -1, 'deleted': 1}},
            {'conv': 'inbox', 'flag': 'restore', 'change': {'archive': 1, 'deleted': -1}},
        ],
        [
            {'conv': 'sent', 'flag': 'inbox', 'change': {'inbox': 1}},
            {'conv': 'sent', 'flag': 'archive', 'change': {'inbox': -1}},
        ],
        [{'conv': 'draft', 'flag': 'inbox', 'status': 400, 'message': 'deleted, spam or draft conversation cannot'}],
        [{'conv': 'draft', 'flag': 'archive', 'status': 409, 'message': 'conversation not in inbox'}],
        [{'conv': 'inbox_unseen', 'mark_seen': True, 'change': {'unseen': -1}}],
        [
            {'conv': 'inbox_unseen', 'flag': 'archive', 'change': {'inbox': -1, 'unseen': -1, 'archive': 1}},
            {'conv': 'inbox_unseen', 'mark_seen': True},
        ],
    ],
)
async def test_set_flag(cli, factory: Factory, conns, user_actions):
    user = await factory.create_user()
    other_user = await factory.create_user()
    p = [{'email': user.email}]

    convs = {
        'draft': await factory.create_conv(),
        'sent': await factory.create_conv(publish=True),
        'inbox_unseen': await factory.create_conv(publish=True, session_id=other_user.session_id, participants=p),
        'inbox': await factory.create_conv(publish=True, session_id=other_user.session_id, participants=p),
    }
    await factory.act(user.id, convs['inbox'].id, ActionModel(act=ActionTypes.seen))

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 2, 'unseen': 1, 'draft': 1, 'sent': 1, 'archive': 0, 'all': 4, 'spam': 0, 'deleted': 0}

    for i, action in enumerate(user_actions):
        conv = action['conv']
        if action.get('mark_seen'):
            await factory.act(user.id, convs[conv].id, ActionModel(act=ActionTypes.seen))
            counts_new = await get_flag_counts(conns, user.id)
        else:
            flag = action['flag']
            r = await cli.post_json(
                factory.url('ui:set-conv-flag', conv=convs[conv].key, query={'flag': flag}),
                status=action.get('status', 200),
            )
            obj = await r.json()
            if r.status != 200:
                assert obj['message'].startswith(action['message']), i
                continue
            counts_new = obj['counts']
        changes = {}
        for k, v in counts_new.items():
            diff = v - counts[k]
            if diff:
                changes[k] = diff
        assert changes == action.get('change', {}), (i, counts_new)
        counts = counts_new
        true_counts = await get_flag_counts(conns, factory.user.id, force_update=True)
        assert true_counts == counts


@pytest.fixture(name='conv')
async def _fix_conv(cli, factory: Factory, db_conn):
    await factory.create_user()
    creator = await factory.create_user()
    prts = [{'email': factory.user.email}]
    conv = await factory.create_conv(session_id=creator.session_id, publish=True, participants=prts)
    assert 2 == await db_conn.fetchval('select count(*) from participants')
    return conv


async def test_flags_inbox(cli, factory: Factory, conv, db_conn, conns):
    u_id = factory.user.id
    flags = await get_flag_counts(conns, u_id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='archive')))
    assert await r.json() == {
        'conv_flags': {'inbox': False, 'archive': True, 'deleted': False, 'spam': False},
        'counts': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 1, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='inbox')))
    assert await r.json() == {
        'conv_flags': {'inbox': True, 'archive': False, 'deleted': False, 'spam': False},
        'counts': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select inbox from participants where user_id=$1', u_id) is True


async def test_flags_deleted(cli, factory: Factory, db_conn, conv):
    u_id = factory.user.id
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='delete')))
    assert await r.json() == {
        'conv_flags': {'inbox': False, 'archive': False, 'deleted': True, 'spam': False},
        'counts': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 1},
    }
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is True
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) == CloseToNow()

    r = await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query=dict(flag='restore')))
    assert await r.json() == {
        'conv_flags': {'inbox': True, 'archive': False, 'deleted': False, 'spam': False},
        'counts': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }
    assert await db_conn.fetchval('select deleted from participants where user_id=$1', u_id) is None
    assert await db_conn.fetchval('select deleted_ts from participants where user_id=$1', u_id) is None


async def test_seen(factory: Factory, conv, conns):
    flags = await get_flag_counts(conns, factory.user.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(factory.user.id, conv.id, ActionModel(act=ActionTypes.seen))

    flags = await get_flag_counts(conns, factory.user.id)
    assert flags == {'inbox': 1, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    # already seen, shouldn't change seen count
    await factory.act(factory.user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='testing'))

    flags = await get_flag_counts(conns, factory.user.id)
    assert flags == {'inbox': 1, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


flags_empty = {
    'flags': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0},
    'labels': [],
}


async def test_flag_counts_blank(cli, factory: Factory):
    await factory.create_user()
    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == flags_empty


async def test_flag_counts_publish(cli, factory: Factory):
    await factory.create_user()
    u2 = await factory.create_user()

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == flags_empty
    await cli.get_json(factory.url('ui:conv-counts', session_id=u2.session_id))

    await factory.create_conv(publish=True, participants=[{'email': u2.email}])

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == {
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
        'labels': [],
    }
    obj = await cli.get_json(factory.url('ui:conv-counts', session_id=u2.session_id))
    assert obj == {
        'flags': {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
        'labels': [],
    }


async def test_send_reply(factory: Factory, conns):
    user = await factory.create_user()

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    other_user = await factory.create_user()
    conv = await factory.create_conv(publish=True, participants=[{'email': other_user.email}])

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(other_user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='testing'))

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_send_delete_reply(cli, factory: Factory, conns):
    user = await factory.create_user()

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    other_user = await factory.create_user()
    conv = await factory.create_conv(publish=True, participants=[{'email': other_user.email}])

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await cli.post_json(factory.url('ui:set-conv-flag', conv=conv.key, query={'flag': 'delete'}))

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 1}

    await factory.act(other_user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='testing'))

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_flag_counts_draft_publish(cli, factory: Factory, db_conn):
    await factory.create_user()
    u2 = await factory.create_user()

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == flags_empty
    await cli.get_json(factory.url('ui:conv-counts', session_id=u2.session_id))

    await factory.create_conv(participants=[{'email': u2.email}])

    assert 1 == await db_conn.fetchval('select count(*) from participants where user_id=$1', u2.id)
    assert True is await db_conn.fetchval('select inbox from participants where user_id=$1', u2.id)
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', u2.id)

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == {
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
        'labels': [],
    }
    obj = await cli.get_json(factory.url('ui:conv-counts', session_id=u2.session_id))
    assert obj == flags_empty

    await cli.post_json(factory.url('ui:publish', conv=factory.conv.key), {'publish': True})

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj == {
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
        'labels': [],
    }
    assert 1 == await db_conn.fetchval('select count(*) from participants where user_id=$1', u2.id)
    assert True is await db_conn.fetchval('select inbox from participants where user_id=$1', u2.id)
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', u2.id)


async def test_flag_counts(cli, factory: Factory, db_conn, redis):
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
    obj = await cli.get_json(factory.url('ui:conv-counts', session_id=new_user.session_id))
    assert obj == {
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
async def test_filter_flags_conv_list(cli, factory: Factory, db_conn, query, expected):
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
    data = await cli.get_json(url)
    response = [c['details']['sub'] for c in data['conversations']]
    assert response == expected, f'url: {url}, response: {response}'

    data2 = await cli.get_json(url)
    assert data == data2

    if query:
        return
    # all case check results
    d = {
        c['details']['sub']: {
            'seen': int(c['seen']),  # use ints so the below fits on one line each
            'inbox': int(c['inbox']),
            'archive': int(c['archive']),
            'deleted': int(c['deleted']),
            'spam': int(c['spam']),
            'draft': int(c['draft']),
            'sent': int(c['sent']),
        }
        for c in data['conversations']
    }
    assert d == {
        'anne': {'seen': 0, 'inbox': 0, 'archive': 0, 'deleted': 0, 'spam': 1, 'draft': 0, 'sent': 0},
        'ben': {'seen': 0, 'inbox': 0, 'archive': 1, 'deleted': 0, 'spam': 0, 'draft': 0, 'sent': 0},
        'charlie': {'seen': 0, 'inbox': 1, 'archive': 0, 'deleted': 0, 'spam': 0, 'draft': 0, 'sent': 0},
        'dave': {'seen': 0, 'inbox': 0, 'archive': 0, 'deleted': 1, 'spam': 0, 'draft': 0, 'sent': 0},
        'ed': {'seen': 1, 'inbox': 0, 'archive': 0, 'deleted': 0, 'spam': 0, 'draft': 1, 'sent': 0},
        'fred': {'seen': 1, 'inbox': 0, 'archive': 0, 'deleted': 0, 'spam': 0, 'draft': 0, 'sent': 1},
        'george': {'seen': 1, 'inbox': 1, 'archive': 0, 'deleted': 0, 'spam': 0, 'draft': 0, 'sent': 0},
    }


async def test_draft_counts(factory: Factory, conns):
    user = await factory.create_user()
    user2 = await factory.create_user()
    await factory.create_conv(participants=[{'email': user2.email}])

    flags = await get_flag_counts(conns, user.id)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}


async def test_published_counts(factory: Factory, conns):
    user = await factory.create_user()
    user2 = await factory.create_user()
    await factory.create_conv(publish=True, participants=[{'email': user2.email}])

    flags = await get_flag_counts(conns, user.id)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 1, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_add_prt(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(factory.user.id, conv.id, ActionModel(act=ActionTypes.msg_add, body='testing'))

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_add_remove_add_prt(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 0, 'spam': 0, 'deleted': 0}

    f = await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_remove, participant=user2.email, follows=f[0]))

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}

    await factory.act(user.id, conv.id, ActionModel(act=ActionTypes.prt_add, participant=user2.email))

    flags = await get_flag_counts(conns, user2.id)
    assert flags == {'inbox': 1, 'unseen': 1, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0}


async def test_spam_seen(factory: Factory, conns, cli, url, create_ses_email):
    user = await factory.create_user()

    msg = create_ses_email(to=(user.email,), receipt_extra=dict(spamVerdict={'status': 'FAIL'}))
    r = await cli.post(url('protocol:webhook-ses', token='testing'), json=msg)
    assert r.status == 204, await r.text()

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}

    conv_id = await conns.main.fetchval('select id from conversations')
    await factory.act(user.id, conv_id, ActionModel(act=ActionTypes.seen))

    counts = await get_flag_counts(conns, user.id)
    assert counts == {'inbox': 0, 'unseen': 0, 'draft': 0, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 1, 'deleted': 0}

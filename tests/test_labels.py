from urllib.parse import urlencode

import pytest

from .conftest import Factory


def query_display(v):
    try:
        return urlencode(v)
    except TypeError:
        return ','.join(v)


@pytest.mark.parametrize(
    'query, expected',
    [
        ({}, ['dave', 'charlie', 'ben', 'anne']),
        ({'labels_all': 'label1'}, ['dave', 'ben']),
        ([('labels_all', 'label1'), ('labels_all', 'label2')], ['dave']),
        ([('labels_any', 'label1'), ('labels_any', 'label2')], ['dave', 'charlie', 'ben']),
    ],
    ids=query_display,
)
async def test_filter_labels_conv_list(cli, factory: Factory, db_conn, query, expected):
    await factory.create_user()
    test_user = await factory.create_user()

    label1 = await factory.create_label('Label 1')
    label2 = await factory.create_label('Label 2')
    prts = [{'email': test_user.email}]

    await factory.create_conv(subject='anne', participants=prts, publish=True)

    conv_ben = await factory.create_conv(subject='ben', participants=prts, publish=True)
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1], conv_ben.id)

    conv_charlie = await factory.create_conv(subject='charlie', participants=prts, publish=True)
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label2], conv_charlie.id)

    conv_dave = await factory.create_conv(subject='dave', participants=prts, publish=True)
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1, label2], conv_dave.id)

    assert 4 == await db_conn.fetchval('select count(*) from conversations')
    assert 4 == await db_conn.fetchval('select count(*) from participants where user_id=$1', test_user.id)

    url = factory.url('ui:list', session_id=test_user.session_id, query=query)
    url = str(url).replace('label1', str(label1)).replace('label2', str(label2))
    data = await cli.get_json(url)
    response = [c['details']['sub'] for c in data['conversations']]
    assert response == expected, f'url: {url}, response: {response}'

    data2 = await cli.get_json(url)
    assert data == data2


async def test_label_counts(cli, factory: Factory, db_conn):
    await factory.create_user()

    label1 = await factory.create_label('Label 1')
    label2 = await factory.create_label('Label 2', ordering=1)
    label3 = await factory.create_label('Label 3')
    label4 = await factory.create_label('Label 4')

    await factory.create_conv(subject='anne')

    conv_ben = await factory.create_conv(subject='ben')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1], conv_ben.id)

    conv_charlie = await factory.create_conv(subject='charlie')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1, label2], conv_charlie.id)

    conv_dave = await factory.create_conv(subject='dave')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1, label2, label3], conv_dave.id)

    obj = await cli.get_json(factory.url('ui:conv-counts'))
    assert obj['labels'] == [
        {'id': label1, 'name': 'Label 1', 'color': None, 'description': None, 'count': 3},
        {'id': label3, 'name': 'Label 3', 'color': None, 'description': None, 'count': 1},
        {'id': label4, 'name': 'Label 4', 'color': None, 'description': None, 'count': 0},
        {'id': label2, 'name': 'Label 2', 'color': None, 'description': None, 'count': 2},
    ]


async def test_add_remove_label(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from participants')
    label_id = await factory.create_label()

    r = await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'remove', 'label_id': label_id}), status=409
    )
    assert await r.json() == {'message': 'conversation does not have this label'}
    assert await db_conn.fetchval('select label_ids from participants') is None

    r = await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'add', 'label_id': label_id})
    )
    assert await r.json() == {'status': 'ok'}
    assert await db_conn.fetchval('select label_ids from participants') == [label_id]

    r = await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'add', 'label_id': label_id}), status=409
    )
    assert await r.json() == {'message': 'conversation already has this label'}
    assert await db_conn.fetchval('select label_ids from participants') == [label_id]

    r = await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'remove', 'label_id': label_id})
    )
    assert await r.json() == {'status': 'ok'}
    assert await db_conn.fetchval('select label_ids from participants') == []

    r = await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'remove', 'label_id': -1}), status=400
    )
    assert await r.json() == {'message': 'you do not have this label'}


async def test_add_remove_label_multiple(cli, factory: Factory, db_conn):
    await factory.create_user()
    conv = await factory.create_conv()
    assert 1 == await db_conn.fetchval('select count(*) from participants')
    label1 = await factory.create_label('label 1')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1], conv.id)
    label2 = await factory.create_label('label 2')
    assert await db_conn.fetchval('select label_ids from participants') == [label1]

    await cli.post_json(factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'add', 'label_id': label2}))
    assert await db_conn.fetchval('select label_ids from participants') == [label1, label2]

    await cli.post_json(
        factory.url('ui:add-remove-label', conv=conv.key, query={'action': 'remove', 'label_id': label1})
    )
    assert await db_conn.fetchval('select label_ids from participants') == [label2]


async def test_bread_list(cli, factory: Factory):
    await factory.create_user()

    label1 = await factory.create_label('Label 1', ordering=10, color='red')
    label2 = await factory.create_label('Label 2', color='green', description='foobar')
    obj = await cli.get_json(factory.url('ui:labels-browse'))
    assert obj == {
        'items': [
            {'id': label2, 'name': 'Label 2', 'color': 'green', 'description': 'foobar'},
            {'id': label1, 'name': 'Label 1', 'color': 'red', 'description': None},
        ],
        'count': 2,
        'pages': 1,
    }


async def test_bread_add(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    assert 0 == await db_conn.fetchval('select count(*) from labels')
    await cli.post_json(factory.url('ui:labels-add'), data={'name': 'Test Label'}, status=201)
    assert 1 == await db_conn.fetchval('select count(*) from labels')
    label = dict(await db_conn.fetchrow('select user_id, name, color, description, ordering from labels'))
    assert label == {'user_id': user.id, 'name': 'Test Label', 'color': None, 'description': None, 'ordering': 0}


@pytest.mark.xfail(reason='need to upgrade aiohttp-toolbox')
async def test_bread_edit(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    label = await factory.create_label('Label 1')
    await cli.post_json(factory.url('ui:labels-edit', pk=label), data={'color': 'red', 'ordering': 666})
    label = dict(await db_conn.fetchrow('select user_id, name, color, description, ordering from labels'))
    assert label == {'user_id': user.id, 'name': 'Label 1', 'color': 'red', 'description': None, 'ordering': 0}
    assert 1 == await db_conn.fetchval('select count(*) from labels')


async def test_bread_delete(cli, factory: Factory, db_conn):
    await factory.create_user()

    label1 = await factory.create_label('Label 1')
    label2 = await factory.create_label('Label 2')

    conv1 = await factory.create_conv(subject='conv1')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1], conv1.id)
    conv2 = await factory.create_conv(subject='conv2')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label1, label2], conv2.id)
    assert 2 == await db_conn.fetchval('select count(*) from participants where label_ids @> $1', [label1])

    assert await db_conn.fetchval('select label_ids from participants where conv=$1', conv1.id) == [label1]
    assert await db_conn.fetchval('select label_ids from participants where conv=$1', conv2.id) == [label1, label2]

    assert 2 == await db_conn.fetchval('select count(*) from labels')
    await cli.post_json(factory.url('ui:labels-delete', pk=label1))
    assert [r[0] for r in await db_conn.fetch('select id from labels')] == [label2]
    assert 0 == await db_conn.fetchval('select count(*) from participants where label_ids @> $1', [label1])

    assert await db_conn.fetchval('select label_ids from participants where conv=$1', conv1.id) == []
    assert await db_conn.fetchval('select label_ids from participants where conv=$1', conv2.id) == [label2]


async def test_bread_edit_other_user(cli, factory: Factory, db_conn):
    await factory.create_user()

    user2 = await factory.create_user()
    assert user2.id
    label = await factory.create_label('Label 1', user_id=user2.id)
    assert await db_conn.fetchval('select user_id from labels') == user2.id

    await cli.post_json(factory.url('ui:labels-edit', pk=label), data={'color': 'red'}, status=404)
    assert await db_conn.fetchval('select color from labels') is None


async def test_bread_delete_other_user(cli, factory: Factory, db_conn):
    await factory.create_user()

    user2 = await factory.create_user()
    assert user2.id
    label = await factory.create_label('Label 1', user_id=user2.id)
    assert await db_conn.fetchval('select user_id from labels') == user2.id

    await cli.post_json(factory.url('ui:labels-delete', pk=label), status=404)
    assert 1 == await db_conn.fetchval('select count(*) from labels')

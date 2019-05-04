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
        ({}, ['anne', 'ben', 'charlie', 'dave']),
        ({'labels_all': 'label1'}, ['ben', 'dave']),
        ([('labels_all', 'label1'), ('labels_all', 'label2')], ['dave']),
        ([('labels_any', 'label1'), ('labels_any', 'label2')], ['ben', 'charlie', 'dave']),
        ({'inbox': 'true'}, ['charlie']),
        ({'spam': 'true'}, ['anne']),
        ({'spam': 'false'}, ['ben', 'charlie', 'dave']),
        ({'archive': 'true'}, ['ben']),
        ({'seen': 'true'}, ['anne', 'ben', 'dave']),
        ({'deleted': 'true'}, ['dave']),
    ],
    ids=query_display,
)
async def test_filter_labels_conv_list(cli, factory: Factory, db_conn, query, expected):
    await factory.create_user()

    label1 = await factory.create_label('Label 1')
    label2 = await factory.create_label('Label 2')

    conv_anne = await factory.create_conv(subject='anne')
    await db_conn.execute('update participants set spam=true where conv=$1', conv_anne.id)

    conv_ben = await factory.create_conv(subject='ben')
    await db_conn.execute('update participants set label_ids=$1, inbox=false where conv=$2', [label1], conv_ben.id)

    conv_charlie = await factory.create_conv(subject='charlie')
    await db_conn.execute('update participants set label_ids=$1, seen=false where conv=$2', [label2], conv_charlie.id)

    conv_dave = await factory.create_conv(subject='dave')
    await db_conn.execute(
        'update participants set label_ids=$1, deleted=true where conv=$2', [label1, label2], conv_dave.id
    )

    assert 4 == await db_conn.fetchval('select count(*) from conversations')

    url = str(factory.url('ui:list', query=query)).replace('label1', str(label1)).replace('label2', str(label2))
    r = await cli.get(url)
    assert r.status == 200, await r.text()
    response = [c['details']['sub'] for c in (await r.json())['conversations']]
    assert response == expected, f'url: {url}, response: {response}'


async def test_bread_list(cli, factory: Factory):
    await factory.create_user()

    label1 = await factory.create_label('Label 1', ordering=10, color='red')
    label2 = await factory.create_label('Label 2', color='green', description='foobar')
    r = await cli.get(factory.url('ui:labels-browse'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
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
    r = await cli.post_json(factory.url('ui:labels-add'), data={'name': 'Test Label'})
    assert r.status == 201, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from labels')
    label = dict(await db_conn.fetchrow('select user_id, name, color, description, ordering from labels'))
    assert label == {'user_id': user.id, 'name': 'Test Label', 'color': None, 'description': None, 'ordering': 0}


async def test_bread_edit(cli, factory: Factory, db_conn):
    user = await factory.create_user()

    label = await factory.create_label('Label 1')
    r = await cli.post_json(factory.url('ui:labels-edit', pk=label), data={'color': 'red', 'ordering': 666})
    assert r.status == 200, await r.text()
    label = dict(await db_conn.fetchrow('select user_id, name, color, description, ordering from labels'))
    assert label == {'user_id': user.id, 'name': 'Label 1', 'color': 'red', 'description': None, 'ordering': 0}
    assert 1 == await db_conn.fetchval('select count(*) from labels')


async def test_bread_delete(cli, factory: Factory, db_conn):
    await factory.create_user()

    label = await factory.create_label('Label 1')

    conv1 = await factory.create_conv(subject='conv1')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label], conv1.id)
    conv2 = await factory.create_conv(subject='conv2')
    await db_conn.execute('update participants set label_ids=$1 where conv=$2', [label], conv2.id)
    assert 2 == await db_conn.fetchval('select count(*) from participants where label_ids @> $1', [label])

    assert 1 == await db_conn.fetchval('select count(*) from labels')
    r = await cli.post_json(factory.url('ui:labels-delete', pk=label))
    assert r.status == 200, await r.text()
    assert 0 == await db_conn.fetchval('select count(*) from labels')
    assert 0 == await db_conn.fetchval('select count(*) from participants where label_ids @> $1', [label])


async def test_bread_edit_other_user(cli, factory: Factory, db_conn):
    await factory.create_user()

    user2 = await factory.create_user()
    assert user2.id
    label = await factory.create_label('Label 1', user_id=user2.id)
    assert await db_conn.fetchval('select user_id from labels') == user2.id

    r = await cli.post_json(factory.url('ui:labels-edit', pk=label), data={'color': 'red'})
    assert r.status == 404, await r.text()
    assert await db_conn.fetchval('select color from labels') is None


async def test_bread_delete_other_user(cli, factory: Factory, db_conn):
    await factory.create_user()

    user2 = await factory.create_user()
    assert user2.id
    label = await factory.create_label('Label 1', user_id=user2.id)
    assert await db_conn.fetchval('select user_id from labels') == user2.id

    r = await cli.post_json(factory.url('ui:labels-delete', pk=label))
    assert r.status == 404, await r.text()
    assert 1 == await db_conn.fetchval('select count(*) from labels')

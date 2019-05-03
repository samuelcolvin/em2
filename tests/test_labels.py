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


async def test_list_labels(cli, factory: Factory):
    await factory.create_user()

    label1 = await factory.create_label('Label 1', ordering=10, color='red')
    label2 = await factory.create_label('Label 2', color='green', description='foobar')
    r = await cli.get(factory.url('ui:get-labels'))
    assert r.status == 200, await r.text()
    assert await r.json() == {
        'labels': [
            {'id': label2, 'name': 'Label 2', 'description': 'foobar', 'color': 'green'},
            {'id': label1, 'name': 'Label 1', 'description': None, 'color': 'red'},
        ]
    }

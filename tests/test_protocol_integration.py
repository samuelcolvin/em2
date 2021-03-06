from arq import Worker
from pytest_toolbox.comparison import CloseToNow

from em2.core import Action, ActionTypes, construct_conv

from .conftest import Factory


async def test_publish_em2(factory: Factory, worker: Worker, alt_cli, alt_db_conn, alt_conns):
    await factory.create_user(email='testing@local.example.com')

    recipient = 'recipient@alt.example.com'
    await alt_db_conn.fetchval("insert into auth_users (email, account_status) values ($1, 'active')", recipient)
    assert await alt_db_conn.fetchval('select count(*) from conversations') == 0
    conv = await factory.create_conv(participants=[{'email': recipient}], publish=True)
    assert await worker.run_check(max_burst_jobs=2) == 2

    assert await alt_db_conn.fetchval('select count(*) from conversations') == 1
    user_id = await alt_db_conn.fetchval('select id from users where email=$1', recipient)

    conv = await construct_conv(alt_conns, user_id, conv.key)
    assert conv == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 3,
                'author': 'testing@local.example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            }
        ],
        'participants': {'testing@local.example.com': {'id': 1}, 'recipient@alt.example.com': {'id': 2}},
    }


async def test_em2_second_message(factory: Factory, worker: Worker, alt_factory: Factory, conns, alt_conns):
    a = 'testing@local.example.com'
    await factory.create_user(email=a)

    recip = 'recipient@alt.example.com'
    await alt_factory.create_user(email=recip)
    assert await alt_conns.main.fetchval('select count(*) from users') == 1

    conv = await factory.create_conv(participants=[{'email': recip}], publish=True)
    assert await worker.run_check() == 3
    assert await conns.main.fetchval('select count(*) from conversations') == 1
    assert await conns.main.fetchval('select count(*) from actions') == 4
    assert await alt_conns.main.fetchval('select count(*) from conversations') == 1
    assert await alt_conns.main.fetchval('select count(*) from actions') == 4

    action = Action(actor_id=factory.user.id, act=ActionTypes.msg_add, body='msg 2')
    await factory.act(conv.id, action)
    assert await worker.run_check() == 6

    conv_summary = await construct_conv(conns, factory.user.id, conv.key)
    assert conv_summary == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 3,
                'author': a,
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
            {'ref': 5, 'author': a, 'body': 'msg 2', 'created': CloseToNow(), 'format': 'markdown', 'active': True},
        ],
        'participants': {'testing@local.example.com': {'id': 1}, 'recipient@alt.example.com': {'id': 2}},
    }
    alt_conv_summary = await construct_conv(alt_conns, alt_factory.user.id, conv.key)
    assert conv_summary == alt_conv_summary


async def test_em2_reply(factory: Factory, worker: Worker, alt_factory: Factory, conns, alt_conns, alt_worker: Worker):
    sender = 'sender@local.example.com'
    await factory.create_user(email=sender)

    recip = 'recipient@alt.example.com'
    await alt_factory.create_user(email=recip)

    assert await conns.main.fetchval('select count(*) from conversations') == 0
    assert await alt_conns.main.fetchval('select count(*) from conversations') == 0

    conv = await factory.create_conv(participants=[{'email': recip}], publish=True)

    assert await conns.main.fetchval('select count(*) from conversations') == 1
    assert await conns.main.fetchval('select count(*) from actions') == 4
    assert await alt_conns.main.fetchval('select count(*) from conversations') == 0

    assert await worker.run_check() == 3

    assert await conns.main.fetchval('select count(*) from conversations') == 1
    assert await conns.main.fetchval('select count(*) from actions') == 4
    assert await alt_conns.main.fetchval('select count(*) from conversations') == 1
    assert await alt_conns.main.fetchval('select count(*) from actions') == 4

    assert await alt_worker.run_check() == 1
    action = Action(actor_id=alt_factory.user.id, act=ActionTypes.msg_add, body='msg 3')
    alt_conv_id = await alt_conns.main.fetchval('select id from conversations where key=$1', conv.key)
    await alt_factory.act(alt_conv_id, action)

    assert await conns.main.fetchval('select count(*) from actions') == 4
    assert await alt_conns.main.fetchval('select count(*) from actions') == 4

    assert await alt_worker.run_check() == 2

    assert await conns.main.fetchval('select count(*) from actions') == 5
    assert await alt_conns.main.fetchval('select count(*) from actions') == 4

    assert await worker.run_check() == 6

    assert await conns.main.fetchval('select count(*) from actions') == 5
    assert await alt_conns.main.fetchval('select count(*) from actions') == 5

    conv_summary = await construct_conv(conns, factory.user.id, conv.key)
    assert conv_summary == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 3,
                'author': 'sender@local.example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
            {
                'ref': 5,
                'author': 'recipient@alt.example.com',
                'body': 'msg 3',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
        ],
        'participants': {'sender@local.example.com': {'id': 1}, 'recipient@alt.example.com': {'id': 2}},
    }
    alt_conv_summary = await construct_conv(alt_conns, alt_factory.user.id, conv.key)
    assert conv_summary == alt_conv_summary

from arq import Worker
from pytest_toolbox.comparison import CloseToNow

from em2.core import construct_conv

from .conftest import Factory


async def test_publish_em2(factory: Factory, worker: Worker, alt_server, alt_db_conn, alt_conns):
    await factory.create_user(email='testing@local.example.com')

    recipient = 'recipient@alt.example.com'
    await alt_db_conn.fetchval(
        "insert into auth_users (email, account_status) values ($1, 'active') returning id", recipient
    )
    assert await alt_db_conn.fetchval('select count(*) from conversations') == 0
    conv = await factory.create_conv(participants=[{'email': recipient}], publish=True)
    assert await worker.run_check(max_burst_jobs=2) == 2

    assert await alt_db_conn.fetchval('select count(*) from conversations') == 1
    user_id = await alt_db_conn.fetchval('select id from users where email=$1', recipient)

    conv = await construct_conv(alt_conns, user_id, conv.key)
    assert conv == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [{'ref': 3, 'body': 'Test Message', 'created': CloseToNow(), 'format': 'markdown', 'active': True}],
        'participants': {'testing@local.example.com': {'id': 1}, 'recipient@alt.example.com': {'id': 2}},
    }

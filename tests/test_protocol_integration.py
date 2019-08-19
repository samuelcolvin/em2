from arq import Worker

from .conftest import Factory


async def test_publish_em2(factory: Factory, db_conn, worker: Worker, cli, alt_server, alt_db_conn):

    await factory.create_user(email='testing@local.example.com')

    recipient = 'recipient@alt.example.com'
    await alt_db_conn.fetchval(
        "insert into auth_users (email, account_status) values ($1, 'active') returning id", recipient
    )
    await factory.create_conv(participants=[{'email': recipient}], publish=True)
    # assert await worker.run_check(max_burst_jobs=2) == 2

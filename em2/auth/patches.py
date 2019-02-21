from argparse import ArgumentParser
from getpass import getpass

from atoolbox import patch
from atoolbox.db.helpers import run_sql_section

from .utils import mk_password


@patch
async def create_user(*, conn, settings, args, logger, **kwargs):
    """
    Create a new user
    """
    parser = ArgumentParser(description='create a new user')
    for f in ('email', 'first_name', 'last_name', 'password'):
        parser.add_argument(f'--{f}')

    ns = parser.parse_args(args)
    ns.email = ns.email or input('enter email address: ')
    ns.first_name = ns.first_name or input('enter first name: ')
    ns.last_name = ns.last_name or input('enter last name: ')
    ns.password = ns.password or getpass('enter password: ')

    password_hash = mk_password(ns.password, settings)

    user_id = await conn.fetchval(
        """
        insert into auth_users (email, first_name, last_name, password_hash, account_status)
        values ($1, $2, $3, $4, 'active')
        on conflict (email) do nothing
        returning id
        """,
        ns.email,
        ns.first_name,
        ns.last_name,
        password_hash,
    )
    if not user_id:
        logger.error('user with email address %s already exists', ns.email_address)
    else:
        logger.info('user %d created', user_id)


@patch
async def update_action_insert(*, conn, settings, **kwargs):
    await run_sql_section('action-insert', settings.sql_path.read_text(), conn)

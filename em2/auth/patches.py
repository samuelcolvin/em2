from argparse import ArgumentParser
from getpass import getpass

from atoolbox import patch

from .utils import mk_password


@patch
async def create_user(*, conn, settings, args, logger, **kwargs):
    """
    Create a new user
    """
    parser = ArgumentParser(description='create a new user')
    for f in ('email_address', 'first_name', 'last_name', 'password'):
        parser.add_argument(f'--{f}')

    ns = parser.parse_args(args)
    ns.email_address = ns.email_address or input('enter email address: ')
    ns.first_name = ns.first_name or input('enter first name: ')
    ns.last_name = ns.last_name or input('enter last name: ')
    ns.password = ns.password or getpass('enter password: ')

    password_hash = mk_password(ns.password, settings)

    user_id = await conn.fetchval(
        """
        INSERT INTO auth_users (address, first_name, last_name, password_hash, account_status)
        VALUES ($1, $2, $3, $4, 'active')
        ON CONFLICT (address) DO NOTHING RETURNING id
        """,
        ns.email_address, ns.first_name, ns.last_name, password_hash
    )
    if not user_id:
        logger.error('user with email address %s already exists', ns.email_address)
    else:
        logger.info('user %d created', user_id)

import hashlib
import secrets
from datetime import datetime
from enum import Enum, unique
from typing import Dict, Set

from buildpg.asyncpg import BuildPgConnection

from em2.utils.datetime import to_unix_ms


@unique
class Components(str, Enum):
    """
    Component types, used for both urls and in db ENUM see models.sql
    """

    conv = 'conv'
    subject = 'subject'
    expiry = 'expiry'
    label = 'label'
    message = 'message'
    participant = 'participant'
    attachment = 'attachment'


@unique
class Verbs(str, Enum):
    """
    Verb types, used for both urls and in db ENUM see models.sql
    """

    publish = 'publish'
    add = 'add'
    modify = 'modify'
    remove = 'remove'
    recover = 'recover'
    lock = 'lock'
    unlock = 'unlock'


@unique
class Relationships(str, Enum):
    sibling = 'sibling'
    child = 'child'


@unique
class MsgFormat(str, Enum):
    markdown = 'markdown'
    plain = 'plain'
    html = 'html'


async def get_create_user(conn: BuildPgConnection, email: str) -> int:
    """
    get a user by email address or create them if they don't yet exist, return their id.
    """

    user_id = await conn.fetchval('select id from users where email = $1', email)
    if user_id is None:
        # update here should happen very rarely
        user_id = await conn.fetchval(
            """
            insert into users (email) values ($1)
            on conflict (email) do update set email=EXCLUDED.email
            returning id
            """,
            email,
        )
    return user_id


async def get_create_multiple_users(conn: BuildPgConnection, emails: Set[str]) -> Dict[str, int]:
    """
    like get_create_user but for multiple users.
    """
    users = dict(await conn.fetch('select email, id from users where email = any($1)', emails))
    remaining = emails - users.keys()

    if remaining:
        v = await conn.fetch(
            """
            insert into users (email) (select unnest ($1::varchar(255)[]))
            on conflict (email) do update set email=excluded.email
            returning email, id
            """,
            remaining,
        )
        users.update(dict(v))
    return users


def generate_conv_key(creator: str, ts: datetime, subject: str) -> str:
    """
    Create hash reference for a conversation. Set when a conversation is published.
    """
    to_hash = f'{creator}_{to_unix_ms(ts)}_{subject}'.encode()
    return hashlib.sha256(to_hash).hexdigest()


def draft_conv_key() -> str:
    """
    Create reference for a draft conversation.
    """
    return secrets.token_hex(10)  # string length will be 20

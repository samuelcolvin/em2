import hashlib
import secrets
from datetime import datetime
from enum import Enum, unique
from typing import Dict, Optional, Set, Tuple

from atoolbox import JsonErrors
from buildpg.asyncpg import BuildPgConnection

from em2.utils.datetime import to_unix_ms


@unique
class ActionsTypes(str, Enum):
    """
    Action types (component and verb), used for both urls and in db ENUM see models.sql
    """

    conv_publish = 'conv:publish'
    conv_create = 'conv:create'
    subject_modify = 'subject:modify'
    expiry_modify = 'expiry:modify'
    message_add = 'message:add'
    message_modify = 'message:modify'
    message_remove = 'message:remove'
    message_recover = 'message:recover'
    message_lock = 'message:lock'
    message_unlock = 'message:unlock'
    prt_add = 'participant:add'
    prt_remove = 'participant:remove'
    prt_modify = 'participant:modify'  # change perms
    # TODO labels, attachments, other models


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


async def get_conv_for_user(conn: BuildPgConnection, user_id: int, conv_key_prefix: str) -> Tuple[int, Optional[int]]:
    """
    Get a conversation id for a user based on the beginning of the conversation key, if the user has been
    removed from the conversation the id of the last action they can see will also be returned.
    """
    conv_key_match = conv_key_prefix + '%'
    r = await conn.fetchrow(
        """
        select c.id, c.published, c.creator from conversations as c
        join participants as p on c.id=p.conv
        where p.user_id=$1 and c.key like $2
        order by c.created_ts desc
        limit 1
        """,
        user_id,
        conv_key_match,
    )
    if r:
        conv_id, published, creator = r
        last_action = None
    else:
        # can happen legitimately when a user was removed from the conversation,
        # but can still view it up to that point
        r = await conn.fetchrow(
            """
            select c.id, c.published, c.creator, a.id from actions as a
            join conversations as c on a.conv = c.id
            join participants as p on a.participant = p.id
            where p.user_id=$1 and c.key like $2 and a.component='participant' and a.verb='remove'
            order by c.created_ts desc, a.id desc
            limit 1
            """,
            user_id,
            conv_key_match,
        )
        if r:
            conv_id, published, creator, last_action = r
        else:
            raise JsonErrors.HTTPNotFound(message='Conversation not found')

    if not published and user_id != creator:
        raise JsonErrors.HTTPForbidden(error='conversation is unpublished and you are not the creator')
    return conv_id, last_action

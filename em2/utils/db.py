import hashlib
import secrets
from datetime import datetime, timezone
from typing import Set

get_user_id_sql = 'select id, display_name from users where email = $1'
# update here should happen very rarely
set_user_id_sql = """
insert into users (email, display_name) values ($1, $2)
on conflict (email) do update set display_name=EXCLUDED.display_name
returning id
"""
update_user_display_name = 'update users set display_name=$2 where id=$1'


async def get_create_user(conn, email, display_name):
    r = await conn.fetchrow(get_user_id_sql, email)
    if r is None:
        user_id = await conn.fetchval(set_user_id_sql, email, display_name)
    else:
        user_id, previous_display_name = r
        if display_name and previous_display_name != display_name:
            await conn.execute(update_user_display_name, user_id, display_name)
    return user_id


get_existing_recips_sql = 'SELECT email, id FROM users WHERE email = any($1)'
set_missing_recips_sql = """
INSERT INTO users (email) (SELECT unnest ($1::VARCHAR(255)[]))
ON CONFLICT (email) DO UPDATE SET email=EXCLUDED.email
RETURNING email, id
"""


async def create_missing_users(conn, emails: Set[str]):
    recips = dict(await conn.fetch(get_existing_recips_sql, emails))
    remaining = emails - recips.keys()

    if remaining:
        recips.update(dict(await conn.fetch(set_missing_recips_sql, remaining)))
    return set(recips.values())


EPOCH = datetime(1970, 1, 1)
EPOCH_TZ = EPOCH.replace(tzinfo=timezone.utc)


def to_unix_ms(dt: datetime) -> int:
    if dt.utcoffset() is None:
        diff = dt - EPOCH
    else:
        diff = dt - EPOCH_TZ
    return int(diff.total_seconds() * 1000)


def generate_conv_key(creator, ts, subject):
    to_hash = creator, to_unix_ms(ts), subject
    to_hash = '_'.join(map(str, to_hash)).encode()
    return hashlib.sha256(to_hash).hexdigest()


def gen_random(prefix):
    assert len(prefix) == 3
    # 3 + 1 + 8 * 2 == 20
    return prefix + '-' + secrets.token_hex(8)

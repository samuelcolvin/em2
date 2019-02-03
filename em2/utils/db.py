import hashlib
import secrets
from datetime import datetime, timezone
from typing import Set

get_recipient_id_sql = 'select id, display_name from recipients where address = $1'
# update here should happen very rarely
set_recipient_id_sql = """
insert into recipients (address, display_name) values ($1, $2)
on conflict (address) do update set display_name=EXCLUDED.display_name
returning id
"""
update_recipient_display_name = 'update recipients set display_name=$2 where id=$1'


async def get_create_recipient(conn, address, display_name):
    r = await conn.fetchrow(get_recipient_id_sql, address)
    if r is None:
        recipient_id = await conn.fetchval(set_recipient_id_sql, address, display_name)
    else:
        recipient_id, previous_display_name = r
        if display_name and previous_display_name != display_name:
            await conn.execute(update_recipient_display_name, recipient_id, display_name)
    return recipient_id


get_existing_recips_sql = 'SELECT address, id FROM recipients WHERE address = any($1)'
set_missing_recips_sql = """
INSERT INTO recipients (address) (SELECT unnest ($1::VARCHAR(255)[]))
ON CONFLICT (address) DO UPDATE SET address=EXCLUDED.address
RETURNING address, id
"""


async def create_missing_recipients(conn, addresses: Set[str]):
    recips = dict(await conn.fetch(get_existing_recips_sql, addresses))
    remaining = addresses - recips.keys()

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



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

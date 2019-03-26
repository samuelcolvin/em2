"""
raw db tests
"""
import json
from datetime import datetime


async def test_update_conv(db_conn):
    user_id = await db_conn.fetchval("insert into users (email) values ('testing@example.com') returning id")
    ts = datetime.utcnow()
    conv_id = await db_conn.fetchval(
        """
        insert into conversations (key, creator, created_ts, updated_ts)
        values ('key', $1, $2, $2) returning id
        """,
        user_id,
        ts,
    )
    v = dict(await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id))
    assert v == {'details': None, 'last_action_id': 0}

    global_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, body, preview) values "
        "($1, 'message:add', $2, 'msg body', 'msg preview') returning id",
        conv_id,
        user_id,
    )
    assert global_id == 1
    changes = await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id)
    assert changes['last_action_id'] == 1
    assert json.loads(changes['details']) == {
        'act': 'message:add',
        'sub': None,
        'email': 'testing@example.com',
        'prev': 'msg preview',
        'prts': 0,
        'msgs': 1,
    }

    user2_id = await db_conn.fetchval("insert into users (email) values ('second@example.com') returning id")
    await db_conn.fetchval('insert into participants (conv, user_id) values ($1, $2)', conv_id, user2_id)
    global_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, participant_user) values ($1, 'participant:add', $2, $3) returning id",
        conv_id,
        user_id,
        user2_id,
    )
    assert global_id == 2
    changes = await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id)
    assert changes['last_action_id'] == 2
    assert json.loads(changes['details']) == {
        'act': 'participant:add',
        'sub': None,
        'email': 'testing@example.com',
        'prev': 'msg preview',
        'prts': 1,
        'msgs': 1,
    }


# TODO tests for message count and tests for body choices

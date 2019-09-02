"""
raw db tests
"""
import json
from datetime import datetime


async def test_update_conv(db_conn):
    user1_id = await db_conn.fetchval("insert into users (email) values ('testing-1@example.com') returning id")
    user2_id = await db_conn.fetchval("insert into users (email) values ('testing-2@example.com') returning id")
    ts = datetime.utcnow()
    conv_id = await db_conn.fetchval(
        """
        insert into conversations (key, creator, created_ts, updated_ts, live)
        values ('key', $1, $2, $2, true) returning id
        """,
        user1_id,
        ts,
    )
    v = dict(await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id))
    assert v == {'details': None, 'last_action_id': 0}

    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, body, preview) values "
        "($1, 'message:add', $2, 'msg body', 'msg preview') returning id",
        conv_id,
        user2_id,
    )
    assert action_id == 1
    changes = await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id)
    assert changes['last_action_id'] == 1
    assert json.loads(changes['details']) == {
        'act': 'message:add',
        'sub': None,
        'creator': 'testing-1@example.com',
        'email': 'testing-2@example.com',
        'prev': 'msg preview',
        'prts': 0,
        'msgs': 1,
    }

    user3_id = await db_conn.fetchval("insert into users (email) values ('third@example.com') returning id")
    await db_conn.fetchval('insert into participants (conv, user_id) values ($1, $2)', conv_id, user3_id)
    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, participant_user) values ($1, 'participant:add', $2, $3) returning id",
        conv_id,
        user2_id,
        user3_id,
    )
    assert action_id == 2
    changes = await db_conn.fetchrow('select details, last_action_id from conversations where id=$1', conv_id)
    assert changes['last_action_id'] == 2
    assert json.loads(changes['details']) == {
        'act': 'participant:add',
        'sub': None,
        'creator': 'testing-1@example.com',
        'email': 'testing-2@example.com',
        'prev': 'msg preview',
        'prts': 1,
        'msgs': 1,
    }


async def test_last_action_id(db_conn):
    user_id = await db_conn.fetchval("insert into users (email) values ('testing-1@example.com') returning id")
    ts = datetime.utcnow()
    conv_id = await db_conn.fetchval(
        """
        insert into conversations (key, creator, created_ts, updated_ts, live)
        values ('key', $1, $2, $2, true) returning id
        """,
        user_id,
        ts,
    )
    assert await db_conn.fetchval('select last_action_id from conversations where id=$1', conv_id) == 0

    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, body) values ($1, 'message:add', $2, 'x') returning id",
        conv_id,
        user_id,
    )
    assert action_id == 1
    assert await db_conn.fetchval('select last_action_id from conversations where id=$1', conv_id) == 1

    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, body, id) values ($1, 'message:add', $2, 'x', 10) returning id",
        conv_id,
        user_id,
    )
    assert action_id == 10
    assert await db_conn.fetchval('select last_action_id from conversations where id=$1', conv_id) == 10

    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor) values ($1, 'seen', $2) returning id", conv_id, user_id
    )
    assert action_id == 11
    assert await db_conn.fetchval('select last_action_id from conversations where id=$1', conv_id) == 11

    action_id = await db_conn.fetchval(
        "insert into actions (conv, act, actor, id) values ($1, 'seen', $2, 20) returning id", conv_id, user_id
    )
    assert action_id == 20
    assert await db_conn.fetchval('select last_action_id from conversations where id=$1', conv_id) == 20


# TODO tests for message count and tests for body choices

import json
import logging
from typing import List

import pytest
from arq import Worker
from atoolbox import JsonErrors
from pydantic import ValidationError
from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import ActionModel, ActionTypes, apply_actions, construct_conv

from .conftest import Factory


async def act(conn, settings, actor_user_id, conv_prefix, action) -> List[int]:
    return (await apply_actions(conn, settings, actor_user_id, conv_prefix, [action]))[1]


async def test_msg_add(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval('select count(*) from actions')

    action = ActionModel(act=ActionTypes.msg_add, body='This is a test')
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)
    action_info = dict(await db_conn.fetchrow('select * from actions where id=4'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 4,
        'conv': conv.id,
        'act': 'message:add',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': None,
        'participant_user': None,
        'body': 'This is a test',
        'parent': None,
        'msg_format': 'markdown',
    }


async def test_msg_lock_msg(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval("select id from actions where act='message:add'")

    assert [4] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=2))
    action_info = dict(await db_conn.fetchrow('select * from actions where id=4'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 4,
        'conv': conv.id,
        'act': 'message:lock',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': await db_conn.fetchval('select pk from actions where id=2'),
        'participant_user': None,
        'body': None,
        'parent': None,
        'msg_format': None,
    }


async def test_msg_add_child(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionTypes.msg_add, body='This is a child message', parent=2)
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)
    action_info = dict(await db_conn.fetchrow('select * from actions where id=4'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 4,
        'conv': conv.id,
        'act': 'message:add',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': None,
        'participant_user': None,
        'body': 'This is a child message',
        'parent': await db_conn.fetchval('select pk from actions where id=2'),
        'msg_format': 'markdown',
    }


async def test_msg_delete_recover(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_delete, follows=2))
    assert [5] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_recover, follows=4))

    fields = ', '.join(['id', 'conv', 'act', 'actor', 'follows'])
    actions_info = [dict(r) for r in await db_conn.fetch(f'select {fields} from actions where id>=4 order by id')]
    assert actions_info == [
        {
            'id': 4,
            'conv': conv.id,
            'act': 'message:delete',
            'actor': user.id,
            'follows': await db_conn.fetchval('select pk from actions where id=2'),
        },
        {
            'id': 5,
            'conv': conv.id,
            'act': 'message:recover',
            'actor': user.id,
            'follows': await db_conn.fetchval('select pk from actions where id=4'),
        },
    ]


async def test_msg_lock_modify(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=2))

    action = ActionModel(act=ActionTypes.msg_modify, follows=4, body='modified body')
    assert [5] == await act(db_conn, settings, user.id, conv.key, action)

    fields = ', '.join(['id', 'conv', 'act', 'actor', 'follows', 'body'])
    actions_info = [dict(r) for r in await db_conn.fetch(f'select {fields} from actions where id>=4 order by id')]
    assert actions_info == [
        {
            'id': 4,
            'conv': conv.id,
            'act': 'message:lock',
            'actor': user.id,
            'follows': await db_conn.fetchval('select pk from actions where id=2'),
            'body': None,
        },
        {
            'id': 5,
            'conv': conv.id,
            'act': 'message:modify',
            'actor': user.id,
            'follows': await db_conn.fetchval('select pk from actions where id=4'),
            'body': 'modified body',
        },
    ]


async def test_participant_add(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)
    action_info = dict(await db_conn.fetchrow('select * from actions where id=4'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 4,
        'conv': conv.id,
        'act': 'participant:add',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': None,
        'participant_user': await db_conn.fetchval("select id from users where email='new@example.com'"),
        'body': None,
        'parent': None,
        'msg_format': None,
    }


async def test_participant_remove(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)

    action = ActionModel(act=ActionTypes.prt_remove, participant='new@example.com', follows=4)
    assert [5] == await act(db_conn, settings, user.id, conv.key, action)
    action_info = dict(await db_conn.fetchrow('select * from actions where id=5'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 5,
        'conv': conv.id,
        'act': 'participant:remove',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': await db_conn.fetchval('select pk from actions where id=4'),
        'participant_user': await db_conn.fetchval("select id from users where email='new@example.com'"),
        'body': None,
        'parent': None,
        'msg_format': None,
    }


async def test_msg_conflict_follows(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=2))

    action = ActionModel(act=ActionTypes.msg_modify, follows=2, body='modified body')
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await act(db_conn, settings, user.id, conv.key, action)
    assert exc_info.value.message == 'other actions already follow action 2'


async def test_msg_follows_wrong(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval("select id from actions where act='conv:create'")

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=3))
    assert exc_info.value.message == '"follows" action has the wrong type'


async def test_msg_recover_not_locked(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_recover, follows=2))
    assert exc_info.value.message == 'message:recover can only occur on a deleted message'


async def test_msg_modify_not_locked(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_modify, follows=2, body='x'))
    assert exc_info.value.message == 'message:modify must follow message:lock by the same user'


async def test_msg_delete_lock(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_delete, follows=2))

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=4))
    assert exc_info.value.message == 'only message:recover can occur on a deleted message'


async def test_msg_locked_delete(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    action = ActionModel(act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)

    assert [5] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=2))

    user2_id = await db_conn.fetchval("select id from users where email='new@example.com'")
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionTypes.msg_delete, follows=5))
    assert exc_info.value.message == 'message locked, action not possible'


async def test_not_on_conv(factory: Factory, db_conn, settings):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()

    with pytest.raises(JsonErrors.HTTPNotFound) as exc_info:
        await act(db_conn, settings, user2.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=2))
    assert exc_info.value.message == 'Conversation not found'


async def test_participant_add_exists(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)

    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await act(db_conn, settings, user.id, conv.key, action)

    assert exc_info.value.message == 'user already a participant in this conversation'


async def test_participant_remove_yourself(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionTypes.prt_remove, participant=user.email, follows=1)
    with pytest.raises(JsonErrors.HTTPForbidden) as exc_info:
        await act(db_conn, settings, user.id, conv.key, action)
    assert exc_info.value.message == 'You cannot modify your own participant'


async def test_bad_action():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.conv_publish)
    assert exc_info.value.errors() == [{'loc': ('act',), 'msg': 'Action not permitted', 'type': 'value_error'}]


async def test_bad_participant_missing():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.prt_add)

    assert 'participant is required for participant actions' in exc_info.value.json()


async def test_bad_participant_included():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.msg_add, participant='new@example.com')

    assert 'participant must be omitted except for participant actions' in exc_info.value.json()


async def test_bad_no_body():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.msg_add)
    assert 'body is required for message:add and message:modify' in exc_info.value.json()


async def test_bad_body_included():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.prt_remove, participant='new@example.com', follows=1, body='should be here')
    assert 'body must be omitted except for message:add and message:modify' in exc_info.value.json()


async def test_bad_no_follows():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.prt_remove, participant='new@example.com')
    assert 'follows is required for this action' in exc_info.value.json()


async def test_object_simple(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_add, body='This is a reply'))

    obj = await construct_conv(db_conn, user.id, conv.key)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {'ref': 2, 'body': 'Test Message', 'created': CloseToNow(), 'format': 'markdown', 'active': True},
            {'ref': 4, 'body': 'This is a reply', 'created': CloseToNow(), 'format': 'markdown', 'active': True},
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }


async def test_object_children(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_add, body='This is a reply'))
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_add, body='child1', parent=4))
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_add, body='child2', parent=5))

    assert [7] == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_lock, follows=5))
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_modify, follows=7, body='mod1'))

    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.msg_delete, follows=2))

    obj = await construct_conv(db_conn, user.id, conv.key)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {'ref': 9, 'body': 'Test Message', 'created': CloseToNow(), 'format': 'markdown', 'active': False},
            {
                'ref': 4,
                'body': 'This is a reply',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
                'children': [
                    {
                        'ref': 8,
                        'body': 'mod1',
                        'created': CloseToNow(),
                        'format': 'markdown',
                        'active': True,
                        'children': [
                            {'ref': 6, 'body': 'child2', 'created': CloseToNow(), 'format': 'markdown', 'active': True}
                        ],
                    }
                ],
            },
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }


async def test_object_add_remove_participants(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='new@ex.com'))
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='new2@ex.com'))
    action = ActionModel(act=ActionTypes.prt_remove, participant='new2@ex.com', follows=5)
    await act(db_conn, settings, user.id, conv.key, action)
    obj = await construct_conv(db_conn, user.id, conv.key)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [{'ref': 2, 'body': 'Test Message', 'created': CloseToNow(), 'format': 'markdown', 'active': True}],
        'participants': {'testing-1@example.com': {'id': 1}, 'new@ex.com': {'id': 4}},
    }


async def test_participant_add_cant_get(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    user2 = await factory.create_user()

    action = ActionModel(act=ActionTypes.prt_add, participant=user2.email)
    assert [4] == await act(db_conn, settings, user.id, conv.key, action)
    obj = await construct_conv(db_conn, user.id, conv.key)
    assert obj['participants'] == {'testing-1@example.com': {'id': 1}, 'testing-2@example.com': {'id': 4}}

    with pytest.raises(JsonErrors.HTTPForbidden) as exc_info:
        await construct_conv(db_conn, user2.id, conv.key)
    assert exc_info.value.message == 'conversation is unpublished and you are not the creator'


async def test_seen(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)

    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='2@ex.com'))
    updated_ts1, details = await db_conn.fetchrow('select updated_ts, details from conversations where id=$1', conv.id)
    assert json.loads(details) == {
        'act': 'participant:add',
        'sub': 'Test Subject',
        'email': 'testing-1@example.com',
        'body': 'Test Message',
        'prts': 2,
        'msgs': 1,
    }

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    user2_id = await db_conn.fetchval('select id from users where email=$1', '2@ex.com')
    assert False is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionTypes.seen))

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    updated_ts2, details = await db_conn.fetchrow('select updated_ts, details from conversations where id=$1', conv.id)
    assert json.loads(details) == {
        'act': 'participant:add',
        'sub': 'Test Subject',
        'email': 'testing-1@example.com',
        'body': 'Test Message',
        'prts': 2,
        'msgs': 1,
    }
    assert updated_ts1 == updated_ts2  # update_ts didn't change on seen actions

    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='3@ex.com'))

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    assert False is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)


async def test_already_seen(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='2@ex.com'))

    user2_id = await db_conn.fetchval('select id from users where email=$1', '2@ex.com')
    assert False is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    assert None is not await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionTypes.seen))
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    assert [] == await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionTypes.seen))
    await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionTypes.prt_add, participant='3@ex.com'))
    assert False is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)
    assert [7] == await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionTypes.seen))
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)


async def test_participant_add_many(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    for i in range(63):
        action = ActionModel(act=ActionTypes.prt_add, participant=f'new-{i}@example.com')
        await act(db_conn, settings, user.id, conv.key, action)

    assert 64 == await db_conn.fetchval('select count(*) from participants where conv=$1', conv.id)

    action = ActionModel(act=ActionTypes.prt_add, participant=f'too-many@example.com')
    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, action)
    assert exc_info.value.message == 'no more than 64 participants permitted'


async def test_publish_remote(factory: Factory, redis, db_conn, worker: Worker, caplog):
    caplog.set_level(logging.INFO)
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'whatever@remote.com'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (2, 0, 0)
    job_results = await redis.all_job_results()
    assert len(job_results) == 2
    push_job = next(j for j in job_results if j['function'] == 'push_actions')
    assert push_job['result'] == 'retry=0 fallback=1 em2=0'

    log = '\n'.join(r.message for r in caplog.records)
    assert "testing-1@example.com > {'whatever@remote.com'}\n  Subject: Test Subject" in log

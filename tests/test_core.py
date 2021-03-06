import json
import logging

import pytest
from arq import Worker
from atoolbox import JsonErrors
from pydantic import ValidationError
from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import Action, ActionTypes, construct_conv
from em2.ui.views.conversations import ActionModel

from .conftest import Factory


async def test_msg_add(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval('select count(*) from actions')

    action = Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a **test**')
    assert [4] == await factory.act(conv.id, action)
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
        'body': 'This is a **test**',
        'preview': 'This is a test',
        'parent': None,
        'msg_format': 'markdown',
        'warnings': None,
    }


async def test_msg_lock_msg(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval("select id from actions where act='message:add'")

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=2))
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
        'preview': None,
        'parent': None,
        'msg_format': None,
        'warnings': None,
    }


async def test_msg_add_child(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a child message', parent=2)
    assert [4] == await factory.act(conv.id, action)
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
        'preview': 'This is a child message',
        'parent': await db_conn.fetchval('select pk from actions where id=2'),
        'msg_format': 'markdown',
        'warnings': None,
    }


async def test_msg_delete_recover(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_delete, follows=2))
    assert [5] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_recover, follows=4))

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


async def test_msg_lock_modify(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=2))

    action = Action(actor_id=user.id, act=ActionTypes.msg_modify, follows=4, body='modified body')
    assert [5] == await factory.act(conv.id, action)

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


async def test_participant_add(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)
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
        'preview': None,
        'parent': None,
        'msg_format': None,
        'warnings': None,
    }


async def test_participant_remove(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)

    action = Action(actor_id=user.id, act=ActionTypes.prt_remove, participant='new@example.com', follows=4)
    assert [5] == await factory.act(conv.id, action)
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
        'preview': None,
        'parent': None,
        'msg_format': None,
        'warnings': None,
    }


async def test_msg_conflict_follows(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=2))

    action = Action(actor_id=user.id, act=ActionTypes.msg_modify, follows=2, body='modified body')
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await factory.act(conv.id, action)
    assert exc_info.value.message == 'other actions already follow action 2'


async def test_msg_follows_wrong(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval("select id from actions where act='conv:create'")

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=3))
    assert exc_info.value.message == '"follows" action has the wrong type'


async def test_msg_recover_not_locked(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_recover, follows=2))
    assert exc_info.value.message == 'message:recover can only occur on a deleted message'


async def test_msg_modify_not_locked(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_modify, follows=2, body='x'))
    assert exc_info.value.message == 'message:modify must follow message:lock by the same user'


async def test_msg_delete_lock(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_delete, follows=2))

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=4))
    assert exc_info.value.message == 'only message:recover can occur on a deleted message'


async def test_msg_locked_delete(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)

    assert [5] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=2))

    user2_id = await db_conn.fetchval("select id from users where email='new@example.com'")
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await factory.act(conv.id, Action(actor_id=user2_id, act=ActionTypes.msg_delete, follows=5))
    assert exc_info.value.message == 'message locked, action not possible'


async def test_not_on_conv(factory: Factory):
    await factory.create_user()
    conv = await factory.create_conv(publish=True)

    user2 = await factory.create_user()

    with pytest.raises(JsonErrors.HTTPNotFound) as exc_info:
        await factory.act(conv.id, Action(actor_id=user2.id, act=ActionTypes.msg_lock, follows=2))
    assert exc_info.value.message == 'Conversation not found'


async def test_participant_add_exists(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com')
    assert [4] == await factory.act(conv.id, action)

    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await factory.act(conv.id, action)

    assert exc_info.value.message == 'user already a participant in this conversation'


async def test_participant_remove_yourself(factory: Factory):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = Action(actor_id=user.id, act=ActionTypes.prt_remove, participant=user.email, follows=1)
    with pytest.raises(JsonErrors.HTTPForbidden) as exc_info:
        await factory.act(conv.id, action)
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
    assert 'body is required for message:add, message:modify and subject:modify' in exc_info.value.json()


async def test_bad_body_included():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.prt_remove, participant='new@example.com', follows=1, body='should be here')
    assert 'body must be omitted except for message:add, message:modify and subject:modify' in exc_info.value.json()


async def test_bad_no_follows():
    with pytest.raises(ValidationError) as exc_info:
        ActionModel(act=ActionTypes.prt_remove, participant='new@example.com')
    assert 'follows is required for this action' in exc_info.value.json()


async def test_object_simple(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a reply'))

    obj = await construct_conv(conns, user.id, conv.id)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 2,
                'author': 'testing-1@example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
            {
                'ref': 4,
                'author': 'testing-1@example.com',
                'body': 'This is a reply',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            },
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }


async def test_object_children(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a reply'))
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='child1', parent=4))
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='child2', parent=5))

    assert [7] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_lock, follows=5))
    assert [8] == await factory.act(
        conv.id, Action(actor_id=user.id, act=ActionTypes.msg_modify, follows=7, body='mod1')
    )

    assert [9] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_delete, follows=2))

    obj = await construct_conv(conns, user.id, conv.id)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 9,
                'author': 'testing-1@example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': False,
            },
            {
                'ref': 4,
                'author': 'testing-1@example.com',
                'body': 'This is a reply',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
                'children': [
                    {
                        'ref': 8,
                        'body': 'mod1',
                        'author': 'testing-1@example.com',
                        'created': CloseToNow(),
                        'format': 'markdown',
                        'active': True,
                        'editors': ['testing-1@example.com'],
                        'children': [
                            {
                                'ref': 6,
                                'author': 'testing-1@example.com',
                                'body': 'child2',
                                'created': CloseToNow(),
                                'format': 'markdown',
                                'active': True,
                            }
                        ],
                    }
                ],
            },
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }


async def test_object_add_remove_participants(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@ex.com'))
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new2@ex.com'))
    action = Action(actor_id=user.id, act=ActionTypes.prt_remove, participant='new2@ex.com', follows=5)
    await factory.act(conv.id, action)
    obj = await construct_conv(conns, user.id, conv.key)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 2,
                'author': 'testing-1@example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            }
        ],
        'participants': {'testing-1@example.com': {'id': 1}, 'new@ex.com': {'id': 4}},
    }


async def test_participant_add_cant_get(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()
    user2 = await factory.create_user()

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant=user2.email)
    assert [4] == await factory.act(conv.id, action)
    obj = await construct_conv(conns, user.id, conv.key)
    assert obj['participants'] == {'testing-1@example.com': {'id': 1}, 'testing-2@example.com': {'id': 4}}

    with pytest.raises(JsonErrors.HTTPForbidden) as exc_info:
        await construct_conv(conns, user2.id, conv.key)
    assert exc_info.value.message == 'conversation is unpublished and you are not the creator'


async def test_seen(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)

    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='2@ex.com'))
    updated_ts1, details = await db_conn.fetchrow('select updated_ts, details from conversations where id=$1', conv.id)
    assert json.loads(details) == {
        'act': 'participant:add',
        'sub': 'Test Subject',
        'creator': 'testing-1@example.com',
        'email': 'testing-1@example.com',
        'prev': 'Test Message',
        'prts': 2,
        'msgs': 1,
    }

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    user2_id = await db_conn.fetchval('select id from users where email=$1', '2@ex.com')
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    await factory.act(conv.id, Action(actor_id=user2_id, act=ActionTypes.seen))

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    updated_ts2, details = await db_conn.fetchrow('select updated_ts, details from conversations where id=$1', conv.id)
    assert json.loads(details) == {
        'act': 'participant:add',
        'sub': 'Test Subject',
        'creator': 'testing-1@example.com',
        'email': 'testing-1@example.com',
        'prev': 'Test Message',
        'prts': 2,
        'msgs': 1,
    }
    assert updated_ts1 == updated_ts2  # update_ts didn't change on seen actions

    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='3@ex.com'))

    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user.id)
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)


async def test_already_seen(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='2@ex.com'))

    user2_id = await db_conn.fetchval('select id from users where email=$1', '2@ex.com')
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    assert None is not await factory.act(conv.id, Action(actor_id=user2_id, act=ActionTypes.seen))
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)

    assert [] == await factory.act(conv.id, Action(actor_id=user2_id, act=ActionTypes.seen))
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='3@ex.com'))
    assert None is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)
    assert [7] == await factory.act(conv.id, Action(actor_id=user2_id, act=ActionTypes.seen))
    assert True is await db_conn.fetchval('select seen from participants where user_id=$1', user2_id)


async def test_participant_add_many(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    for i in range(63):
        action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant=f'new-{i}@example.com')
        await factory.act(conv.id, action)

    assert 64 == await db_conn.fetchval('select count(*) from participants where conv=$1', conv.id)

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant=f'too-many@example.com')
    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await factory.act(conv.id, action)
    assert exc_info.value.message == 'no more than 64 participants permitted'


async def test_publish_remote(factory: Factory, redis, db_conn, worker: Worker, caplog):
    caplog.set_level(logging.INFO)
    await factory.create_user()
    await factory.create_conv(participants=[{'email': 'whatever@example.net'}], publish=True)
    assert 4 == await db_conn.fetchval('select count(*) from actions')
    await worker.async_run()
    assert (worker.jobs_complete, worker.jobs_failed, worker.jobs_retried) == (3, 0, 0)
    job_results = await redis.all_job_results()
    assert len(job_results) == 3
    push_job = next(j for j in job_results if j.function == 'push_actions')
    assert push_job.result == 'retry=0 smtp=1 em2=0'

    log = '\n'.join(r.message for r in caplog.records)
    assert "testing-1@example.com > whatever@example.net\n  Subject: Test Subject" in log


async def test_publish_seen(factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval('select count(*) from actions')

    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.seen))
    assert 4 == await db_conn.fetchval('select count(*) from actions')

    obj = await construct_conv(conns, user.id, conv.id)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 2,
                'author': 'testing-1@example.com',
                'body': 'Test Message',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
            }
        ],
        'participants': {'testing-1@example.com': {'id': 1}},
    }


actions_summary_sql = """
select a.id, af.id as follows, a.act, a.body from actions a
join actions af on a.follows=af.pk
where a.id>3
"""


async def test_subject_modify(factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert 3 == await db_conn.fetchval('select id from actions where act=$1', ActionTypes.conv_create)

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.subject_lock, follows=3))
    assert [5] == await factory.act(
        conv.id, Action(actor_id=user.id, act=ActionTypes.subject_modify, follows=4, body='new subject')
    )

    actions_info = [dict(r) for r in await db_conn.fetch(actions_summary_sql)]
    assert actions_info == [
        {'id': 4, 'follows': 3, 'act': 'subject:lock', 'body': None},
        {'id': 5, 'follows': 4, 'act': 'subject:modify', 'body': 'new subject'},
    ]
    obj = await construct_conv(conns, user.id, conv.id)
    assert obj['subject'] == 'new subject'


async def test_subject_lock_release(factory: Factory, db_conn, conns):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert 3 == await db_conn.fetchval('select id from actions where act=$1', ActionTypes.conv_create)

    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.subject_lock, follows=3))
    assert [5] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.subject_release, follows=4))

    actions_info = [dict(r) for r in await db_conn.fetch(actions_summary_sql)]
    assert actions_info == [
        {'id': 4, 'follows': 3, 'act': 'subject:lock', 'body': None},
        {'id': 5, 'follows': 4, 'act': 'subject:release', 'body': None},
    ]
    obj = await construct_conv(conns, user.id, conv.id)
    assert obj['subject'] == 'Test Subject'


async def test_prt_add_remove_add(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()

    em = 'new@example.com'
    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant=em)
    assert [4] == await factory.act(conv.id, action)
    new_user_id = await db_conn.fetchval('select id from users where email=$1', em)
    prt = dict(
        await db_conn.fetchrow('select removal_action_id, seen, inbox from participants where user_id=$1', new_user_id)
    )
    assert prt == {'removal_action_id': None, 'seen': None, 'inbox': True}

    action = Action(actor_id=user.id, act=ActionTypes.prt_remove, participant=em, follows=4)
    assert [5] == await factory.act(conv.id, action)

    prt = await db_conn.fetchrow(
        'select removal_action_id, removal_details, seen, inbox from participants where user_id=$1', new_user_id
    )
    prt = dict(prt)
    removal_details = json.loads(prt.pop('removal_details'))
    assert removal_details == {
        'act': 'participant:remove',
        'sub': 'Test Subject',
        'email': 'testing-1@example.com',
        'creator': 'testing-1@example.com',
        'prev': 'Test Message',
        'prts': 2,
        'msgs': 1,
    }
    assert prt == {'removal_action_id': 5, 'seen': None, 'inbox': True}

    action = Action(actor_id=user.id, act=ActionTypes.prt_add, participant=em)
    assert [6] == await factory.act(conv.id, action)

    action_info = dict(await db_conn.fetchrow('select * from actions where id=6'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 6,
        'conv': conv.id,
        'act': 'participant:add',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': None,
        'participant_user': new_user_id,
        'body': None,
        'preview': None,
        'parent': None,
        'msg_format': None,
        'warnings': None,
    }
    prt = await db_conn.fetchrow(
        'select removal_action_id, removal_details, seen, inbox from participants where user_id=$1', new_user_id
    )
    assert dict(prt) == {'removal_action_id': None, 'removal_details': None, 'seen': None, 'inbox': True}


async def test_prt_add_act(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant='new@example.com'))

    new_user_id = await db_conn.fetchval('select id from users where email=$1', 'new@example.com')
    await factory.act(conv.id, Action(actor_id=new_user_id, act=ActionTypes.msg_add, body='This is a **test**'))


async def test_prt_remove_cant_act(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    em = 'new@example.com'
    assert [4] == await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant=em))
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_remove, participant=em, follows=4))

    new_user_id = await db_conn.fetchval('select id from users where email=$1', em)

    with pytest.raises(JsonErrors.HTTPBadRequest):
        await factory.act(conv.id, Action(actor_id=new_user_id, act=ActionTypes.msg_add, body='This is a **test**'))


async def test_msg_modify_editors(factory: Factory, conns):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    em = 'new@example.com'
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.prt_add, participant=em))

    new_user_id = await conns.main.fetchval('select id from users where email=$1', em)

    assert [5] == await factory.act(conv.id, Action(actor_id=new_user_id, act=ActionTypes.msg_lock, follows=2))

    action = Action(actor_id=new_user_id, act=ActionTypes.msg_modify, follows=5, body='modified body')
    assert [6] == await factory.act(conv.id, action)

    obj = await construct_conv(conns, user.id, conv.id)
    assert obj == {
        'subject': 'Test Subject',
        'created': CloseToNow(),
        'messages': [
            {
                'ref': 6,
                'author': 'testing-1@example.com',
                'body': 'modified body',
                'created': CloseToNow(),
                'format': 'markdown',
                'active': True,
                'editors': ['new@example.com'],
            }
        ],
        'participants': {'testing-1@example.com': {'id': 1}, 'new@example.com': {'id': 4}},
    }


async def test_msg_add_not_live(factory: Factory, db_conn):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a **test**'))

    await db_conn.fetchval('update conversations set live=false')

    with pytest.raises(JsonErrors.HTTPNotFound):
        await factory.act(conv.id, Action(actor_id=user.id, act=ActionTypes.msg_add, body='This is a **test**'))

import pytest
from atoolbox import JsonErrors
from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.core import ActionModel, ActionsTypes, act

from .conftest import Factory


async def test_msg_add(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval('select count(*) from actions')

    action = ActionModel(act=ActionsTypes.msg_add, body='This is a test')
    assert 4 == await act(db_conn, settings, user.id, conv.key, action)
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
        'msg_parent': None,
        'msg_format': 'markdown',
    }


async def test_msg_lock_msg(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 2 == await db_conn.fetchval("select id from actions where act='message:add'")

    assert 4 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=2))
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
        'msg_parent': None,
        'msg_format': None,
    }


async def test_msg_add_child(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    action = ActionModel(act=ActionsTypes.msg_add, body='This is a child message', msg_parent=2)
    assert 4 == await act(db_conn, settings, user.id, conv.key, action)
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
        'msg_parent': await db_conn.fetchval('select pk from actions where id=2'),
        'msg_format': 'markdown',
    }


async def test_msg_delete_recover(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert 4 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_delete, follows=2))
    assert 5 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_recover, follows=4))

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

    assert 4 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=2))

    action = ActionModel(act=ActionsTypes.msg_modify, follows=4, body='modified body')
    assert 5 == await act(db_conn, settings, user.id, conv.key, action)

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

    action = ActionModel(act=ActionsTypes.prt_add, participant='new-participant@example.com')
    assert 4 == await act(db_conn, settings, user.id, conv.key, action)
    action_info = dict(await db_conn.fetchrow('select * from actions where id=4'))
    assert action_info == {
        'pk': AnyInt(),
        'id': 4,
        'conv': conv.id,
        'act': 'participant:add',
        'actor': user.id,
        'ts': CloseToNow(),
        'follows': None,
        'participant_user': await db_conn.fetchval("select id from users where email='new-participant@example.com'"),
        'body': None,
        'msg_parent': None,
        'msg_format': None,
    }


async def test_msg_conflict_follows(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert 4 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=2))

    action = ActionModel(act=ActionsTypes.msg_modify, follows=2, body='modified body')
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await act(db_conn, settings, user.id, conv.key, action)
    assert exc_info.value.message == 'other actions already follow action 2'


async def test_msg_follows_wrong(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()
    assert 3 == await db_conn.fetchval("select id from actions where act='conv:create'")

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=3))
    assert exc_info.value.message == 'message action must follow another message action'


async def test_msg_recover_not_locked(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_recover, follows=2))
    assert exc_info.value.message == 'message:recover can only occur on a deleted message'


async def test_msg_modify_not_locked(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_modify, follows=2, body='x'))
    assert exc_info.value.message == 'message:modify must follow message:lock by the same user'


async def test_msg_delete_lock(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv()

    assert 4 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_delete, follows=2))

    with pytest.raises(JsonErrors.HTTPBadRequest) as exc_info:
        await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=4))
    assert exc_info.value.message == 'only message:recover can occur on a deleted message'


async def test_msg_locked_delete(factory: Factory, db_conn, settings):
    user = await factory.create_user()
    conv = await factory.create_conv(publish=True)

    action = ActionModel(act=ActionsTypes.prt_add, participant='new-participant@example.com')
    assert 4 == await act(db_conn, settings, user.id, conv.key, action)

    assert 5 == await act(db_conn, settings, user.id, conv.key, ActionModel(act=ActionsTypes.msg_lock, follows=2))

    user2_id = await db_conn.fetchval("select id from users where email='new-participant@example.com'")
    with pytest.raises(JsonErrors.HTTPConflict) as exc_info:
        await act(db_conn, settings, user2_id, conv.key, ActionModel(act=ActionsTypes.msg_delete, follows=5))
    assert exc_info.value.message == 'message locked, action not possible'

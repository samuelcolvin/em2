import hashlib
import json
import secrets
from datetime import datetime
from enum import Enum, unique
from typing import Any, Dict, List, Optional, Set, Tuple

from atoolbox import JsonErrors
from buildpg import V
from buildpg.asyncpg import BuildPgConnection
from pydantic import BaseModel, EmailStr, constr, validator

from .settings import Settings
from .utils.datetime import to_unix_ms
from .utils.db import or404


@unique
class ActionsTypes(str, Enum):
    """
    Action types (component and verb), used for both urls and in db ENUM see models.sql
    """

    conv_publish = 'conv:publish'
    conv_create = 'conv:create'
    subject_modify = 'subject:modify'
    subject_lock = 'subject:lock'
    subject_release = 'subject:release'
    expiry_modify = 'expiry:modify'
    msg_add = 'message:add'
    msg_modify = 'message:modify'
    msg_delete = 'message:delete'
    msg_recover = 'message:recover'
    msg_lock = 'message:lock'
    msg_release = 'message:release'
    prt_add = 'participant:add'
    prt_remove = 'participant:remove'
    prt_modify = 'participant:modify'  # change perms
    # TODO labels, attachments, other models


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


async def get_conv_for_user(
    conn: BuildPgConnection, user_id: int, conv_key_prefix: str
) -> Tuple[int, Optional[int], bool]:
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
        conv_id, published, creator, last_action = await or404(
            conn.fetchrow(
                """
                select c.id, c.published, c.creator, a.id from actions as a
                join conversations as c on a.conv = c.id
                where c.key like $2 and a.participant_user=$1 and a.act='participant:remove'
                order by c.created_ts desc, a.id desc
                limit 1
                """,
                user_id,
                conv_key_match,
            ),
            msg='Conversation not found',
        )

    if not published and user_id != creator:
        raise JsonErrors.HTTPForbidden('conversation is unpublished and you are not the creator')
    return conv_id, last_action, published


_prt_action_types = {a for a in ActionsTypes if a.value.startswith('participant:')}
_msg_action_types = {a for a in ActionsTypes if a.value.startswith('message:')}
_follow_action_types = (_msg_action_types - {ActionsTypes.msg_add}) | {ActionsTypes.prt_modify, ActionsTypes.prt_remove}


class ActionModel(BaseModel):
    """
    Representation of an action to perform.
    """

    act: ActionsTypes
    participant: Optional[EmailStr] = None
    body: Optional[constr(min_length=1, max_length=2000, strip_whitespace=True)] = None
    follows: Optional[int] = None
    msg_parent: Optional[int] = None
    msg_format: MsgFormat = MsgFormat.markdown

    @validator('act')
    def check_act(cls, v):
        if v in {ActionsTypes.conv_publish, ActionsTypes.conv_create}:
            raise ValueError('Action not permitted')
        return v

    @validator('participant', always=True)
    def check_participant(cls, v, values, **kwargs):
        act: ActionsTypes = values.get('act')
        if act and not v and act in _prt_action_types:
            raise ValueError('participant is required for participant actions')
        if act and v and act not in _prt_action_types:
            raise ValueError('participant must be omitted except for participant actions')
        return v

    @validator('body', always=True)
    def check_body(cls, v, values, **kwargs):
        act: ActionsTypes = values.get('act')
        if act and v is None and act in {ActionsTypes.msg_add, ActionsTypes.msg_modify}:
            raise ValueError('body is required for message:add and message:modify')
        if act and v is not None and act not in {ActionsTypes.msg_add, ActionsTypes.msg_modify}:
            raise ValueError('body must be omitted except for message:add and message:modify')
        return v

    @validator('follows', always=True)
    def check_follows(cls, v, values, **kwargs):
        act: ActionsTypes = values.get('act')
        if act and v is None and act in _follow_action_types:
            raise ValueError('follows is required for this action')
        return v


class _Act:
    """
    See act() below for details.
    """

    __slots__ = ('conn', 'settings', 'actor_user_id', 'action', 'conv_id')

    def __init__(self, conn: BuildPgConnection, settings: Settings, actor_user_id: int, action: ActionModel):
        self.conn = conn
        self.settings = settings
        self.actor_user_id = actor_user_id
        self.action = action
        self.conv_id = None

    async def run(self, conv_prefix: str) -> int:
        self.conv_id, last_action, _ = await get_conv_for_user(self.conn, self.actor_user_id, conv_prefix)
        if last_action:
            # if the usr has be removed from the conversation they can't act
            raise JsonErrors.HTTPNotFound(message='Conversation not found')

        async with self.conn.transaction():
            if self.action.act in _prt_action_types:
                action_id = await self._act_on_participant()
            elif self.action.act in _msg_action_types:
                action_id = await self._act_on_message()
            else:
                raise NotImplementedError

        return action_id

    async def _act_on_participant(self) -> int:
        follows_pk = None
        if self.action.act == ActionsTypes.prt_add:
            prt_user_id = await get_create_user(self.conn, self.action.participant)
            prt_id = await self.conn.fetchval(
                """
                insert into participants (conv, user_id) values ($1, $2)
                on conflict (conv, user_id) do nothing returning id
                """,
                self.conv_id,
                prt_user_id,
            )
            if not prt_id:
                raise JsonErrors.HTTPConflict('user already a participant in this conversation')
        else:
            follows_pk, *_ = await self.get_follows({ActionsTypes.prt_add, ActionsTypes.prt_modify})
            if self.action.act == ActionsTypes.prt_remove:
                prt_id, prt_user_id = await or404(
                    self.conn.fetchrow(
                        """
                        select p.id, u.id from participants as p join users as u on p.user_id = u.id
                        where conv=$1 and email=$2
                        """,
                        self.conv_id,
                        self.action.participant,
                    ),
                    msg='user not found on conversation',
                )

                await self.conn.execute('delete from participants where id=$1', prt_id)
            else:
                raise NotImplementedError('"participant:modify" not yet implemented')

        # can't do anything to yourself
        if prt_user_id == self.actor_user_id:
            raise JsonErrors.HTTPForbidden('You cannot modify your own participant')

        return await self.conn.fetchval(
            """
            insert into actions (conv, act, actor, follows, participant_user)
            values              ($1  , $2 , $3   , $4     , $5)
            returning id
            """,
            self.conv_id,
            self.action.act,
            self.actor_user_id,
            follows_pk,
            prt_user_id,
        )

    async def _act_on_message(self) -> int:
        if self.action.act == ActionsTypes.msg_add:
            msg_parent_pk = None
            if self.action.msg_parent:
                # just check tha msg_parent really is an action on this conversation of type message:add
                msg_parent_pk = await or404(
                    self.conn.fetchval(
                        "select pk from actions where conv=$1 and id=$2 and act='message:add'",
                        self.conv_id,
                        self.action.msg_parent,
                    ),
                    msg='msg_parent action not found',
                )
            # no extra checks required, you can add a message even after a deleted message, this avoids complex
            # checks that no message in the hierarchy has been deleted
            return await self.conn.fetchval(
                """
                insert into actions (conv, act          , actor, body, msg_parent, msg_format)
                values              ($1  , 'message:add', $2   , $3  , $4        , $5)
                returning id
                """,
                self.conv_id,
                self.actor_user_id,
                self.action.body,
                msg_parent_pk,
                self.action.msg_format,
            )

        follows_pk, follows_act, follows_actor, follows_age = await self.get_follows(_msg_action_types)

        if self.action.act == ActionsTypes.msg_recover:
            if follows_act != ActionsTypes.msg_delete:
                raise JsonErrors.HTTPBadRequest('message:recover can only occur on a deleted message')
        elif self.action.act in {ActionsTypes.msg_modify, ActionsTypes.msg_release}:
            if follows_act != ActionsTypes.msg_lock or follows_actor != self.actor_user_id:
                raise JsonErrors.HTTPBadRequest(f'{self.action.act} must follow message:lock by the same user')
        else:
            # just lock and delete here
            if follows_act == ActionsTypes.msg_delete:
                raise JsonErrors.HTTPBadRequest('only message:recover can occur on a deleted message')
            elif (
                follows_act == ActionsTypes.msg_lock
                and follows_actor != self.actor_user_id
                and follows_age <= self.settings.message_lock_duration
            ):
                details = {'loc_duration': self.settings.message_lock_duration}
                raise JsonErrors.HTTPConflict('message locked, action not possible', details=details)

        return await self.conn.fetchval(
            """
            insert into actions (conv, actor, act, body, follows)
            values              ($1  , $2   , $3 , $4  , $5)
            returning id
            """,
            self.conv_id,
            self.actor_user_id,
            self.action.act,
            self.action.body,
            follows_pk,
        )

    async def get_follows(self, permitted_acts: Set[ActionsTypes]) -> Tuple[int, str, int, int]:
        follows_pk, follows_act, follows_actor, follows_age = await or404(
            self.conn.fetchrow(
                """
                select pk, act, actor, extract(epoch from current_timestamp - ts)::int
                from actions where conv=$1 and id=$2
                """,
                self.conv_id,
                self.action.follows,
            ),
            msg='"follows" action not found',
        )
        if follows_act not in permitted_acts:
            raise JsonErrors.HTTPBadRequest('"follows" action has the wrong type')

        # all other actions must directly follow their "follows" action, eg. nothing can have happened that follows
        # that action
        existing = await self.conn.fetchrow(
            'select 1 from actions where conv=$1 and follows=$2', self.conv_id, follows_pk
        )
        if existing:
            # is 409 really the right status to use here?
            raise JsonErrors.HTTPConflict(f'other actions already follow action {self.action.follows}')
        return follows_pk, follows_act, follows_actor, follows_age


async def act(
    conn: BuildPgConnection, settings: Settings, actor_user_id: int, conv_prefix: str, action: ActionModel
) -> int:
    """
    Apply an action and return its id.

    Should be used for both remove platforms adding events and local users adding actions.
    """
    return await _Act(conn, settings, actor_user_id, action).run(conv_prefix)


async def conv_actions_json(conn: BuildPgConnection, user_id: int, conv_prefix: str, since_id: int = None):
    conv_id, last_action, _ = await get_conv_for_user(conn, user_id, conv_prefix)
    where_logic = V('a.conv') == conv_id
    if last_action:
        where_logic &= V('a.id') <= last_action

    if since_id:
        await or404(conn.fetchval('select 1 from actions where conv=$1 and id=$1', conv_id, since_id))
        where_logic &= V('a.id') > since_id

    return await or404(
        conn.fetchval_b(
            """
            select array_to_json(array_agg(json_strip_nulls(row_to_json(t))), true)
            from (
              select a.id as id, a.act as act, a.ts as ts, actor_user.email as actor,
              a.body as body, a.msg_format as msg_format,
              prt_user.email as participant, follows_action.id as follows, parent_action.id as msg_parent
              from actions as a

              join users as actor_user on a.actor = actor_user.id

              left join users as prt_user on a.participant_user = prt_user.id
              left join actions as follows_action on a.follows = follows_action.pk
              left join actions as parent_action on a.msg_parent = parent_action.pk
              where :where
              order by a.id
            ) t;
            """,
            where=where_logic,
        )
    )


async def construct_conv(conn: BuildPgConnection, user_id: int, conv_prefix: str, since_id: int = None):
    actions_json = await conv_actions_json(conn, user_id, conv_prefix, since_id)
    actions = json.loads(actions_json)
    return _construct_conv_actions(actions)


def _construct_conv_actions(actions: List[Dict[str, Any]]) -> Dict[str, Any]:  # noqa: 901
    subject = None
    created = None
    messages = {}
    participants = {}

    for action in actions:
        act: ActionsTypes = action['act']
        action_id: int = action['id']
        if act in {ActionsTypes.conv_publish, ActionsTypes.conv_create}:
            subject = action['body']
            created = action['ts']
        elif act == ActionsTypes.subject_lock:
            subject = action['body']
        elif act == ActionsTypes.msg_add:
            message = {
                'ref': action_id,
                'body': action['body'],
                'created': action['ts'],
                'format': action['msg_format'],
                'parent': action.get('msg_parent'),
                'active': True,
            }
            messages[action_id] = message
        elif act in _msg_action_types:
            message = messages[action['follows']]
            message['ref'] = action_id
            if act == ActionsTypes.msg_modify:
                message['body'] = action['body']
            elif act == ActionsTypes.msg_delete:
                message['active'] = False
            elif act == ActionsTypes.msg_recover:
                message['active'] = True
            messages[action_id] = message
        elif act == ActionsTypes.prt_add:
            participants[action['participant']] = {'id': action_id}  # perms not implemented yet
        elif act == ActionsTypes.prt_remove:
            participants.pop(action['participant'])
        else:
            raise NotImplementedError(f'action "{act}" construction not implemented')

    msg_list = []
    for msg in messages.values():
        parent = msg.pop('parent', -1)
        # if 'parent' is missing (-1 here), msg has already been processed
        if parent != -1:
            if parent:
                parent_msg = messages[parent]
                if 'children' not in parent_msg:
                    parent_msg['children'] = [msg]
                else:
                    parent_msg['children'].append(msg)
            else:
                msg_list.append(msg)

    return {'subject': subject, 'created': created, 'messages': msg_list, 'participants': participants}

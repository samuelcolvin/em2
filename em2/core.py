import asyncio
import hashlib
import json
import re
import secrets
import textwrap
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from aioredis import Redis
from atoolbox import JsonErrors
from bs4 import BeautifulSoup
from buildpg import MultipleValues, V, Values
from buildpg.asyncpg import BuildPgConnection
from pydantic import BaseModel, EmailStr, constr, validator

from .settings import Settings
from .utils.datetime import to_unix_ms, utcnow
from .utils.db import or404

StrInt = Union[str, int]


@unique
class ActionTypes(str, Enum):
    """
    Action types (component and verb), used for both urls and in db ENUM see models.sql
    """

    conv_publish = 'conv:publish'
    conv_create = 'conv:create'
    subject_modify = 'subject:modify'
    subject_lock = 'subject:lock'
    subject_release = 'subject:release'
    seen = 'seen'  # could not save this in the db, and just keep it on the participant, but would break all pushing
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


@unique
class UserTypes(str, Enum):
    new = 'new'
    local = 'local'
    remote_em2 = 'remote_em2'
    remote_other = 'remote_other'


async def get_create_user(conn: BuildPgConnection, email: str, user_type: UserTypes = UserTypes.new) -> int:
    """
    get a user by email address or create them if they don't yet exist, return their id.

    user_type is only set if the user is created.
    """
    user_id = await conn.fetchval('select id from users where email=$1', email)
    if user_id is None:
        # update here should happen very rarely
        user_id = await conn.fetchval(
            """
            insert into users (email, user_type) values ($1, $2)
            on conflict (email) do update set email=EXCLUDED.email
            returning id
            """,
            email,
            user_type,
        )
    return user_id


async def get_create_multiple_users(conn: BuildPgConnection, emails: Set[str]) -> Dict[str, int]:
    """
    like get_create_user but for multiple users.
    """
    users = dict(await conn.fetch('select email, id from users where email=any($1)', emails))
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
    conn: BuildPgConnection, user_id: int, conv_ref: StrInt, *, req_pub: bool = None
) -> Tuple[int, Optional[int]]:
    """
    Get a conversation id for a user based on the beginning of the conversation key, if the user has been
    removed from the conversation the id of the last action they can see will also be returned.
    """
    if isinstance(conv_ref, int):
        query = conn.fetchrow(
            """
            select c.id, c.publish_ts, c.creator, p.removal_action_id from conversations as c
            join participants p on c.id=p.conv
            where p.user_id = $1 and c.id = $2
            order by c.created_ts desc
            """,
            user_id,
            conv_ref,
        )
    else:
        query = conn.fetchrow(
            """
            select c.id, c.publish_ts, c.creator, p.removal_action_id from conversations c
            join participants p on c.id=p.conv
            where p.user_id=$1 and c.key like $2
            order by c.created_ts desc
            limit 1
            """,
            user_id,
            conv_ref + '%',
        )

    conv_id, publish_ts, creator, last_action = await or404(query, msg='Conversation not found')

    if not publish_ts and user_id != creator:
        raise JsonErrors.HTTPForbidden('conversation is unpublished and you are not the creator')
    if req_pub is not None and bool(publish_ts) != req_pub:
        msg = 'Conversation not yet published' if req_pub else 'Conversation already published'
        raise JsonErrors.HTTPBadRequest(msg)
    return conv_id, last_action


async def update_conv_users(conn: BuildPgConnection, conv_id: int) -> List[int]:
    """
    Update v on users participating in a conversation
    """
    v = await conn.fetch(
        """
        update users set v=v + 1 from participants
        where participants.user_id = users.id and participants.conv = $1 and users.user_type = 'local'
        returning participants.user_id
        """,
        conv_id,
    )
    return [r[0] for r in v]


_prt_action_types = {a for a in ActionTypes if a.value.startswith('participant:')}
_subject_action_types = {a for a in ActionTypes if a.value.startswith('subject:')}
_msg_action_types = {a for a in ActionTypes if a.value.startswith('message:')}
_follow_action_types = (
    (_msg_action_types - {ActionTypes.msg_add})
    | {ActionTypes.prt_modify, ActionTypes.prt_remove}
    | _subject_action_types
)
# actions that don't materially change the conversation, and therefore don't effect whether someone has seen it
_meta_action_types = {
    ActionTypes.seen,
    ActionTypes.subject_lock,
    ActionTypes.subject_release,
    ActionTypes.msg_lock,
    ActionTypes.msg_release,
}
max_participants = 64
with_body_actions = {ActionTypes.msg_add, ActionTypes.msg_modify, ActionTypes.subject_modify}


class ActionModel(BaseModel):
    """
    Representation of an action to perform.
    """

    act: ActionTypes
    participant: Optional[EmailStr] = None
    body: Optional[constr(min_length=1, max_length=10000, strip_whitespace=True)] = None
    follows: Optional[int] = None
    parent: Optional[int] = None
    msg_format: MsgFormat = MsgFormat.markdown

    @validator('act')
    def check_act(cls, v):
        if v in {ActionTypes.conv_publish, ActionTypes.conv_create}:
            raise ValueError('Action not permitted')
        return v

    @validator('participant', always=True)
    def check_participant(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and not v and act in _prt_action_types:
            raise ValueError('participant is required for participant actions')
        if act and v and act not in _prt_action_types:
            raise ValueError('participant must be omitted except for participant actions')
        return v

    @validator('body', always=True)
    def check_body(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and v is None and act in with_body_actions:
            raise ValueError('body is required for message:add, message:modify and subject:modify')
        if act and v is not None and act not in with_body_actions:
            raise ValueError('body must be omitted except for message:add, message:modify and subject:modify')
        return v

    @validator('follows', always=True)
    def check_follows(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and v is None and act in _follow_action_types:
            raise ValueError('follows is required for this action')
        return v


@dataclass
class File:
    hash: str
    name: Optional[str]
    content_id: str
    content_disp: str
    content_type: str
    size: int
    content: Optional[bytes] = None
    storage: Optional[str] = None


class _Act:
    """
    See act() below for details.
    """

    __slots__ = 'conn', 'settings', 'actor_user_id', 'conv_id', 'new_user_ids', 'spam', 'warnings', 'last_action'

    def __init__(
        self, conn: BuildPgConnection, settings: Settings, actor_user_id: int, spam: bool, warnings: Dict[str, str]
    ):
        self.conn = conn
        self.settings = settings
        self.actor_user_id = actor_user_id
        self.conv_id = None
        # ugly way of doing this, but less ugly than other approaches
        self.new_user_ids: Set[int] = set()
        self.spam = True if spam else None
        self.warnings = json.dumps(warnings) if warnings else None
        self.last_action = None

    async def prepare(self, conv_ref: StrInt) -> Tuple[int, int]:
        self.conv_id, self.last_action = await get_conv_for_user(self.conn, self.actor_user_id, conv_ref)

        # we must be in a transaction
        # this is a hard check that conversations can only have on act applied at a time
        creator = await self.conn.fetchval(
            'select creator from conversations where id=$1 for no key update', self.conv_id
        )
        return self.conv_id, creator

    async def run(self, action: ActionModel, files: Optional[List[File]]) -> Optional[int]:
        if action.act is ActionTypes.seen:
            return await self._seen()

        # you can mark a conversation as seen when removed, but nothing else
        if self.last_action:
            raise JsonErrors.HTTPBadRequest(message="You can't act on conversations you've been removed from")

        if action.act in _prt_action_types:
            return await self._act_on_participant(action)
        elif action.act in _msg_action_types:
            action_id, action_pk = await self._act_on_message(action)
            if files:
                await create_files(self.conn, files, self.conv_id, action_pk)
            return action_id
        elif action.act in _subject_action_types:
            return await self._act_on_subject(action)

        raise NotImplementedError

    async def _seen(self) -> Optional[int]:
        # could use "parent" to identify what was seen
        last_seen = await self.conn.fetchval(
            """
            select a.id from actions as a
            where a.conv=$1 and act='seen' and actor=$2
            order by id desc
            limit 1
            """,
            self.conv_id,
            self.actor_user_id,
        )
        if last_seen:
            last_real_action = await self.conn.fetchval(
                """
                select id from actions
                where conv = $1 and not (act = any($2::ActionTypes[]))
                order by id desc
                limit 1
                """,
                self.conv_id,
                _meta_action_types,
            )
            if last_real_action and last_seen > last_real_action:
                # conversation already seen by this user since it last changed
                return

        return await self.conn.fetchval(
            """
            insert into actions (conv, actor, act   )
            values              ($1  , $2   , 'seen')
            returning id
            """,
            self.conv_id,
            self.actor_user_id,
        )

    async def _act_on_participant(self, action: ActionModel) -> int:
        follows_pk = None
        if action.act == ActionTypes.prt_add:
            prts_count = await self.conn.fetchval('select count(*) from participants where conv=$1', self.conv_id)
            if prts_count == max_participants:
                raise JsonErrors.HTTPBadRequest(f'no more than {max_participants} participants permitted')

            prt_user_id = await get_create_user(self.conn, action.participant)
            removed_prt_id = await self.conn.fetchval(
                'select id from participants where conv=$1 and user_id=$2 and removal_action_id is not null',
                self.conv_id,
                prt_user_id,
            )
            if removed_prt_id:
                prt_id = removed_prt_id
                await self.conn.execute(
                    """
                    update participants set removal_action_id=null, removal_details=null, removal_updated_ts=null
                    where id=$1
                    """,
                    prt_id,
                )
            else:
                prt_id = await self.conn.fetchval(
                    """
                    insert into participants (conv, user_id, spam) values ($1, $2, $3)
                    on conflict (conv, user_id) do nothing returning id
                    """,
                    self.conv_id,
                    prt_user_id,
                    self.spam,
                )
                if not prt_id:
                    raise JsonErrors.HTTPConflict('user already a participant in this conversation')
                self.new_user_ids.add(prt_user_id)
        else:
            follows_pk, *_ = await self._get_follows(action, {ActionTypes.prt_add, ActionTypes.prt_modify})
            if action.act == ActionTypes.prt_remove:
                prt_id, prt_user_id = await or404(
                    self.conn.fetchrow(
                        """
                        select p.id, u.id from participants as p join users as u on p.user_id = u.id
                        where conv=$1 and email=$2
                        """,
                        self.conv_id,
                        action.participant,
                    ),
                    msg='user not found on conversation',
                )
            else:
                raise NotImplementedError('"participant:modify" not yet implemented')

        # can't do anything to yourself
        if prt_user_id == self.actor_user_id:
            raise JsonErrors.HTTPForbidden('You cannot modify your own participant')

        action_id = await self.conn.fetchval(
            """
            insert into actions (conv, act, actor, follows, participant_user)
            values              ($1  , $2 , $3   , $4     , $5)
            returning id
            """,
            self.conv_id,
            action.act,
            self.actor_user_id,
            follows_pk,
            prt_user_id,
        )
        if action.act == ActionTypes.prt_remove:
            await self.conn.execute(
                """
                update participants p set
                removal_action_id=$1, removal_details=c.details, removal_updated_ts=c.updated_ts
                from conversations c
                where p.id=$2 and p.conv=c.id
                """,
                action_id,
                prt_id,
            )
        return action_id

    async def _act_on_message(self, action: ActionModel) -> Tuple[int, int]:
        if action.act == ActionTypes.msg_add:
            parent_pk = None
            if action.parent:
                # just check tha parent really is an action on this conversation of type message:add
                parent_pk = await or404(
                    self.conn.fetchval(
                        "select pk from actions where conv=$1 and id=$2 and act='message:add'",
                        self.conv_id,
                        action.parent,
                    ),
                    msg='parent action not found',
                )
            # no extra checks required, you can add a message even after a deleted message, this avoids complex
            # checks that no message in the hierarchy has been deleted
            return await self.conn.fetchrow(
                """
                insert into actions (conv, act          , actor, body, preview, parent, msg_format, warnings)
                values              ($1  , 'message:add', $2   , $3  , $4     , $5    , $6        , $7)
                returning id, pk
                """,
                self.conv_id,
                self.actor_user_id,
                action.body,
                message_preview(action.body, action.msg_format),
                parent_pk,
                action.msg_format,
                self.warnings,
            )

        follows_pk, follows_act, follows_actor, follows_age = await self._get_follows(action, _msg_action_types)

        if action.act == ActionTypes.msg_recover:
            if follows_act != ActionTypes.msg_delete:
                raise JsonErrors.HTTPBadRequest('message:recover can only occur on a deleted message')
        elif action.act in {ActionTypes.msg_modify, ActionTypes.msg_release}:
            if follows_act != ActionTypes.msg_lock or follows_actor != self.actor_user_id:
                # TODO lock maybe shouldn't be required when conversation is draft
                raise JsonErrors.HTTPBadRequest(f'{action.act} must follow message:lock by the same user')
        else:
            # just lock and delete here
            if follows_act == ActionTypes.msg_delete:
                raise JsonErrors.HTTPBadRequest('only message:recover can occur on a deleted message')
            elif (
                follows_act == ActionTypes.msg_lock
                and follows_actor != self.actor_user_id
                and follows_age <= self.settings.message_lock_duration
            ):
                details = {'loc_duration': self.settings.message_lock_duration}
                raise JsonErrors.HTTPConflict('message locked, action not possible', details=details)

        return await self.conn.fetchrow(
            """
            insert into actions (conv, actor, act, body, preview, follows)
            values              ($1  , $2   , $3 , $4  , $5     , $6)
            returning id, pk
            """,
            self.conv_id,
            self.actor_user_id,
            action.act,
            action.body,
            message_preview(action.body, action.msg_format) if action.act == ActionTypes.msg_modify else None,
            follows_pk,
        )

    async def _act_on_subject(self, action: ActionModel) -> int:
        follow_types = _subject_action_types | {ActionTypes.conv_create, ActionTypes.conv_publish}
        follows_pk, follows_act, follows_actor, follows_age = await self._get_follows(action, follow_types)

        if action.act == ActionTypes.subject_lock:
            if (
                follows_act == ActionTypes.subject_lock
                and follows_actor != self.actor_user_id
                and follows_age <= self.settings.message_lock_duration
            ):
                details = {'loc_duration': self.settings.message_lock_duration}
                raise JsonErrors.HTTPConflict('subject not locked by you, action not possible', details=details)
        else:
            # modify and release
            if follows_act != ActionTypes.subject_lock or follows_actor != self.actor_user_id:
                raise JsonErrors.HTTPBadRequest(f'{action.act} must follow subject:lock by the same user')

        return await self.conn.fetchval(
            """
            insert into actions (conv, actor, act, body, follows)
            values              ($1  , $2   , $3 , $4  , $5)
            returning id
            """,
            self.conv_id,
            self.actor_user_id,
            action.act,
            action.body,
            follows_pk,
        )

    async def _get_follows(self, action: ActionModel, permitted_acts: Set[ActionTypes]) -> Tuple[int, str, int, int]:
        follows_pk, follows_act, follows_actor, follows_age = await or404(
            self.conn.fetchrow(
                """
                select pk, act, actor, extract(epoch from current_timestamp - ts)::int
                from actions where conv=$1 and id=$2
                """,
                self.conv_id,
                action.follows,
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
            raise JsonErrors.HTTPConflict(f'other actions already follow action {action.follows}')
        return follows_pk, follows_act, follows_actor, follows_age


class ConvFlags(str, Enum):
    inbox = 'inbox'
    unseen = 'unseen'
    draft = 'draft'
    sent = 'sent'
    archive = 'archive'
    all = 'all'
    deleted = 'deleted'
    spam = 'spam'


async def apply_actions(
    conn: BuildPgConnection,
    redis: Redis,
    settings: Settings,
    actor_user_id: int,
    conv_ref: StrInt,
    actions: List[ActionModel],
    spam: bool = False,
    warnings: Dict[str, str] = None,
    files: Optional[List[File]] = None,
) -> Tuple[int, List[int]]:
    """
    Apply actions and return their ids.

    Should be used for both remote platforms adding events and local users adding actions.
    """
    action_ids = []
    act_cls = _Act(conn, settings, actor_user_id, spam, warnings)
    actor_user_id_seen = None
    from_deleted, from_archive, already_inbox = [], [], []
    async with conn.transaction():
        # IMPORTANT we do nothing that could be slow (eg. networking) inside this transaction,
        # as the conv is locked for update from prepare onwards
        conv_id, creator_id = await act_cls.prepare(conv_ref)

        for action in actions:
            action_id = await act_cls.run(action, files)
            if action_id:
                action_ids.append(action_id)

        if action_ids:
            # the actor is assumed to have seen the conversation as they've acted upon it
            actor_user_id_seen = await conn.fetchval(
                'update participants set seen=true where conv=$1 and user_id=$2 and seen is not true returning user_id',
                conv_id,
                actor_user_id,
            )
            # everyone else hasn't seen this action if it's "worth seeing"
            if any(a.act not in _meta_action_types for a in actions):
                from_deleted, from_archive, already_inbox = await user_flag_moves(conn, conv_id, actor_user_id)
            await update_conv_users(conn, conv_id)

    updates = [
        *(
            UpdateFlag(
                u_id,
                [
                    (ConvFlags.deleted, -1),
                    (ConvFlags.inbox, 1),
                    (ConvFlags.unseen, 1),
                    # as the message is no longer deleted it must show in sent for the creator as well as inbox
                    creator_id == u_id and (ConvFlags.sent, 1),
                ],
            )
            for u_id in from_deleted
        ),
        *(
            UpdateFlag(
                u_id,
                [
                    # archive shouldn't be decremented for the user since the conv was never in archive
                    creator_id != u_id and (ConvFlags.archive, -1),
                    (ConvFlags.inbox, 1),
                    (ConvFlags.unseen, 1),
                ],
            )
            for u_id in from_archive
        ),
        *(UpdateFlag(u_id, [(ConvFlags.unseen, 1)]) for u_id in already_inbox if u_id),
    ]
    if spam:
        updates += [UpdateFlag(u_id, [(ConvFlags.spam, 1), (ConvFlags.all, 1)]) for u_id in act_cls.new_user_ids]
    else:
        updates += [
            UpdateFlag(u_id, [(ConvFlags.unseen, 1), (ConvFlags.inbox, 1), (ConvFlags.all, 1)])
            for u_id in act_cls.new_user_ids
        ]

    if actor_user_id_seen:
        updates.append(UpdateFlag(actor_user_id_seen, [(ConvFlags.unseen, -1)]))
    if updates:
        await update_conv_flags(*updates, redis=redis)
    return conv_id, action_ids


async def user_flag_moves(
    conn: BuildPgConnection, conv_id: int, actor_user_id: int
) -> Tuple[List[int], List[int], List[int]]:
    # TODO we'll also need to exclude muted conversations from being moved, while still setting seen=false
    # we could exclude no local users from some of this
    return await conn.fetchrow(
        """
        with conv_prts as (
          select p.id from participants p where conv=$1 and user_id!=$2
        ),
        from_deleted as (
          -- user had previously deleted the conversation, move it back to the inbox
          update participants p set seen=null, inbox=true, deleted=null from conv_prts where
          conv_prts.id=p.id and spam is not true and inbox is not true and p.deleted is true
          returning p.user_id
        ),
        from_archive as (
          -- conversation was previously in the archive for these users, move it back to the inbox
          update participants p set seen=null, inbox=true from conv_prts where
          conv_prts.id=p.id and spam is not true and inbox is not true and p.deleted is not true
          returning p.user_id
        ),
        already_inbox as (
          -- conversation was already in the inbox, just mark it as unseen
          update participants p set seen=null from conv_prts where
          conv_prts.id=p.id and spam is not true and inbox is true and seen is true
          returning p.user_id
        ),
        is_spam as (
          -- conversation is marked as spam, just set it to unseen
          update participants p set seen=null from conv_prts where
          conv_prts.id=p.id and spam is true
          returning p.user_id
        )
        select from_deleted, from_archive, already_inbox
        from (select coalesce(array_agg(user_id), '{}') from_deleted from from_deleted) from_deleted,
             (select coalesce(array_agg(user_id), '{}') from_archive from from_archive) from_archive,
             (select coalesce(array_agg(user_id), '{}') already_inbox from already_inbox) already_inbox
        """,
        conv_id,
        actor_user_id,
    )


async def conv_actions_json(
    conn: BuildPgConnection, user_id: int, conv_ref: StrInt, *, since_id: int = None, inc_seen: bool = False
):
    conv_id, last_action = await get_conv_for_user(conn, user_id, conv_ref)
    where_logic = V('a.conv') == conv_id
    if last_action:
        where_logic &= V('a.id') <= last_action

    if since_id:
        await or404(conn.fetchval('select 1 from actions where conv=$1 and id=$2', conv_id, since_id))
        where_logic &= V('a.id') > since_id

    if not inc_seen:
        where_logic &= V('a.act') != ActionTypes.seen

    return await or404(
        conn.fetchval_b(
            """
            select array_to_json(array_agg(json_strip_nulls(row_to_json(t))), true)
            from (
              select a.id, c.key conv, a.act, a.ts, actor_user.email actor,
              a.body, a.msg_format, a.warnings,
              prt_user.email participant, follows_action.id follows, parent_action.id parent,
              (select array_agg(row_to_json(f))
                from (
                  select content_disp, hash, content_id, name, content_type, size
                  from files
                  where files.action = a.pk
                  order by content_id  -- TODO only used in tests I think, could be removed
                ) f
              ) as files
              from actions as a

              join users as actor_user on a.actor = actor_user.id
              join conversations as c on a.conv = c.id

              left join users as prt_user on a.participant_user = prt_user.id
              left join actions as follows_action on a.follows = follows_action.pk
              left join actions as parent_action on a.parent = parent_action.pk
              where :where
              order by a.id
            ) t
            """,
            where=where_logic,
        )
    )


async def construct_conv(conn: BuildPgConnection, user_id: int, conv_ref: StrInt, since_id: int = None):
    actions_json = await conv_actions_json(conn, user_id, conv_ref, since_id=since_id)
    actions = json.loads(actions_json)
    return _construct_conv_actions(actions)


def _construct_conv_actions(actions: List[Dict[str, Any]]) -> Dict[str, Any]:  # noqa: 901
    subject = None
    created = None
    messages = {}
    participants = {}

    for action in actions:
        act: ActionTypes = action['act']
        action_id: int = action['id']
        if act in {ActionTypes.conv_publish, ActionTypes.conv_create}:
            subject = action['body']
            created = action['ts']
        elif act == ActionTypes.subject_modify:
            subject = action['body']
        elif act == ActionTypes.msg_add:
            messages[action_id] = {
                'ref': action_id,
                'body': action['body'],
                'created': action['ts'],
                'format': action['msg_format'],
                'parent': action.get('parent'),
                'active': True,
            }
        elif act in _msg_action_types:
            message = messages[action['follows']]
            message['ref'] = action_id
            if act == ActionTypes.msg_modify:
                message['body'] = action['body']
            elif act == ActionTypes.msg_delete:
                message['active'] = False
            elif act == ActionTypes.msg_recover:
                message['active'] = True
            messages[action_id] = message
        elif act == ActionTypes.prt_add:
            participants[action['participant']] = {'id': action_id}  # perms not implemented yet
        elif act == ActionTypes.prt_remove:
            participants.pop(action['participant'])
        elif act not in _meta_action_types:
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


class CreateConvModel(BaseModel):
    subject: constr(max_length=255, strip_whitespace=True)
    message: constr(max_length=10000, strip_whitespace=True)
    msg_format: MsgFormat = MsgFormat.markdown
    publish = False

    class Participants(BaseModel):
        email: EmailStr
        name: str = None

    participants: List[Participants] = []

    @validator('participants', whole=True)
    def check_participants_count(cls, v):
        if len(v) > max_participants:
            raise ValueError(f'no more than {max_participants} participants permitted')
        return v


async def create_conv(
    *,
    conn: BuildPgConnection,
    redis: Redis,
    creator_email: str,
    creator_id: int,
    conv: CreateConvModel,
    ts: Optional[datetime] = None,
    spam: bool = False,
    warnings: Dict[str, str] = None,
    files: Optional[List[File]] = None,
) -> Tuple[int, str]:
    ts = ts or utcnow()
    conv_key = generate_conv_key(creator_email, ts, conv.subject) if conv.publish else draft_conv_key()
    async with conn.transaction():
        conv_id = await conn.fetchval(
            """
            insert into conversations (key, creator, publish_ts, created_ts, updated_ts)
            values                    ($1,  $2     , $3        , $4        , $4        )
            on conflict (key) do nothing
            returning id
            """,
            conv_key,
            creator_id,
            ts if conv.publish else None,
            ts,
        )
        if conv_id is None:
            raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')

        # TODO currently only email is used
        participants = set(p.email for p in conv.participants)
        part_users = await get_create_multiple_users(conn, participants)

        await conn.execute(
            'insert into participants (conv, user_id, seen, inbox) (select $1, $2, true, null)', conv_id, creator_id
        )
        other_user_ids = list(part_users.values())
        await conn.execute(
            'insert into participants (conv, user_id, spam) (select $1, unnest($2::int[]), $3)',
            conv_id,
            other_user_ids,
            True if spam else None,
        )
        user_ids = [creator_id] + other_user_ids
        await conn.execute(
            """
            insert into actions (conv, act              , actor, ts, participant_user) (
            select               $1  , 'participant:add', $2   , $3, unnest($4::int[])
            )
            """,
            conv_id,
            creator_id,
            ts,
            user_ids,
        )
        add_action_pk = await conn.fetchval(
            """
            insert into actions (conv, act          , actor, ts, body, preview, msg_format, warnings)
            values              ($1  , 'message:add', $2   , $3, $4  , $5     , $6        , $7)
            returning pk
            """,
            conv_id,
            creator_id,
            ts,
            conv.message,
            message_preview(conv.message, conv.msg_format),
            conv.msg_format,
            json.dumps(warnings) if warnings else None,
        )
        await conn.execute(
            """
            insert into actions (conv, act, actor, ts, body)
            values              ($1  , $2 , $3   , $4, $5)
            """,
            conv_id,
            ActionTypes.conv_publish if conv.publish else ActionTypes.conv_create,
            creator_id,
            ts,
            conv.subject,
        )
        await update_conv_users(conn, conv_id)
        if files:
            await create_files(conn, files, conv_id, add_action_pk)

    if not conv.publish:
        updates = (UpdateFlag(creator_id, [(ConvFlags.draft, 1), (ConvFlags.all, 1)]),)
    elif spam:
        updates = (
            UpdateFlag(creator_id, [(ConvFlags.sent, 1), (ConvFlags.all, 1)]),
            *(UpdateFlag(u_id, [(ConvFlags.spam, 1), (ConvFlags.all, 1)]) for u_id in other_user_ids),
        )
    else:
        updates = (
            UpdateFlag(creator_id, [(ConvFlags.sent, 1), (ConvFlags.all, 1)]),
            *(
                UpdateFlag(u_id, [(ConvFlags.inbox, 1), (ConvFlags.unseen, 1), (ConvFlags.all, 1)])
                for u_id in other_user_ids
            ),
        )

    await update_conv_flags(*updates, redis=redis)
    return conv_id, conv_key


async def create_files(conn: BuildPgConnection, files: List[File], conv_id: int, action_pk: int):
    # TODO cope with repeated content_id
    values = [
        Values(
            conv=conv_id,
            action=action_pk,
            hash=f.hash,
            name=f.name,
            content_id=f.content_id,
            content_disp=f.content_disp,
            content_type=f.content_type,
            size=f.size,
            storage=f.storage,
        )
        for f in files
    ]
    await conn.execute_b('insert into files (:values__names) values :values', values=MultipleValues(*values))


_clean_markdown = [
    (re.compile(r'<.*?>', flags=re.S), ''),
    (re.compile(r'_(\S.*?\S)_'), r'\1'),
    (re.compile(r'\[(.+?)\]\(.*?\)'), r'\1'),
    (re.compile(r'(\*\*|`)'), ''),
    (re.compile(r'^(#+|\*|\d+\.) ', flags=re.M), ''),
]
_clean_all = [
    (re.compile(r'^\s+'), ''),
    (re.compile(r'\s+$'), ''),
    (re.compile(r'[\x00-\x1f\x7f-\xa0]'), ''),
    (re.compile(r'[\t\n]+'), ' '),
    (re.compile(r' {2,}'), ' '),
]


def message_preview(body: str, msg_format: MsgFormat) -> str:
    if msg_format == MsgFormat.markdown:
        preview = body
        for regex, p in _clean_markdown:
            preview = regex.sub(p, preview)
    elif msg_format == MsgFormat.html:
        soup = BeautifulSoup(body, 'html.parser')
        soup = soup.find('body') or soup

        for el_name in ('div.gmail_signature', 'style', 'script'):
            for el in soup.select(el_name):
                el.decompose()
        preview = soup.text
    else:
        assert msg_format == MsgFormat.plain, msg_format
        preview = body

    for regex, p in _clean_all:
        preview = regex.sub(p, preview)
    return textwrap.shorten(preview, width=140, placeholder='…')


conv_flag_count_sql = """
select
  count(*) filter (where inbox is true and deleted is not true and spam is not true) as inbox,
  count(*) filter (where inbox is true and deleted is not true and spam is not true and seen is not true) as unseen,

  count(*) filter (where c.creator = $1 and publish_ts is null and deleted is not true) as draft,
  count(*) filter (where c.creator = $1 and publish_ts is not null and deleted is not true) as sent,
  count(*) filter (
    where inbox is not true and deleted is not true and spam is not true and c.creator != $1
  ) as archive,
  count(*) as "all",
  count(*) filter (where spam is true and deleted is not true) as spam,
  count(*) filter (where deleted is true) as deleted
from participants p
join conversations c on p.conv = c.id
where user_id = $1 and (c.publish_ts is not null or c.creator = $1)
limit 9999
"""

conv_label_count_sql = """
select l.id, count(p)
from labels l
left join participants p on label_ids @> array[l.id]
where l.user_id = $1
group by l.id
order by l.ordering, l.id
"""


def _flags_count_key(user_id: int):
    return f'conv-counts-flags-{user_id}'


async def get_flag_counts(user_id, *, conn: BuildPgConnection, redis: Redis, force_update=False) -> dict:
    """
    Get counts for participant flags. Data is cached to a redis hash and retrieved from there if it exists.
    """
    flag_key = _flags_count_key(user_id)
    flags = await redis.hgetall(flag_key)
    if flags and not force_update:
        flags = {k: int(v) for k, v in flags.items()}
    else:
        flags = dict(await conn.fetchrow(conv_flag_count_sql, user_id))
        tr = redis.multi_exec()
        tr.hmset_dict(flag_key, flags)
        tr.expire(flag_key, 86400)
        await tr.execute()
    return flags


@dataclass
class UpdateFlag:
    user_id: int
    changes: Iterable[Tuple[ConvFlags, int]]


async def update_conv_flags(*updates: UpdateFlag, redis: Redis):
    """
    Increment or decrement counts for participant flags if they exist in the cache, also extends cache expiry.
    """

    async def update(u: UpdateFlag):
        key = _flags_count_key(u.user_id)
        if await redis.exists(key):
            await asyncio.gather(
                redis.expire(key, 86400), *(redis.hincrby(key, c[0].value, c[1]) for c in u.changes if c)
            )

    await asyncio.gather(*(update(u) for u in updates if u))


def _label_count_key(user_id: int):
    return f'conv-counts-labels-{user_id}'


async def get_label_counts(user_id, *, conn: BuildPgConnection, redis: Redis) -> dict:
    """
    Get counts for labels. Data is cached to a redis hash and retrieved from there if it exists.
    """
    label_key = _label_count_key(user_id)
    labels = await redis.hgetall(label_key)
    if labels:
        labels = {k: int(v) for k, v in labels.items()}
    else:
        labels = {str(k): v for k, v in await conn.fetch(conv_label_count_sql, user_id)}
        if labels:
            tr = redis.multi_exec()
            tr.hmset_dict(label_key, labels)
            tr.expire(label_key, 86400)
            await tr.execute()
    return labels

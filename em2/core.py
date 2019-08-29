import asyncio
import hashlib
import json
import secrets
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, unique
from typing import AbstractSet, Any, Dict, Iterable, List, Optional, Set, Tuple, Union

from atoolbox import JsonErrors
from buildpg import MultipleValues, V, Values

from .search import search_create_conv, search_update
from .utils.core import MsgFormat, message_preview
from .utils.datetime import to_unix_ms, utcnow
from .utils.db import Connections, or400, or404

StrInt = Union[str, int]


@unique
class ActionTypes(str, Enum):
    """
    Action types (component and verb), used for both urls and in db ENUM see models.sql
    """

    conv_create = 'conv:create'
    conv_publish = 'conv:publish'
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
class UserTypes(str, Enum):
    new = 'new'
    local = 'local'
    remote_em2 = 'remote_em2'
    remote_other = 'remote_other'


async def get_create_user(conns: Connections, email: str, user_type: UserTypes = UserTypes.new) -> int:
    """
    get a user by email address or create them if they don't yet exist, return their id.

    user_type is only set if the user is created.
    """
    user_id = await conns.main.fetchval('select id from users where email=$1', email)
    if user_id is None:
        # update here should happen very rarely
        user_id = await conns.main.fetchval(
            """
            insert into users (email, user_type) values ($1, $2)
            on conflict (email) do update set email=EXCLUDED.email
            returning id
            """,
            email,
            user_type,
        )
    return user_id


async def get_create_multiple_users(conns: Connections, emails: AbstractSet[str]) -> Dict[str, int]:
    """
    like get_create_user but for multiple users.
    """
    users = dict(await conns.main.fetch('select email, id from users where email=any($1)', emails))
    remaining = emails - users.keys()

    if remaining:
        v = await conns.main.fetch(
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
    conns: Connections, user_id: int, conv_ref: StrInt, *, req_pub: bool = None
) -> Tuple[int, Optional[int]]:
    """
    Get a conversation id for a user based on the beginning of the conversation key, if the user has been
    removed from the conversation the id of the last action they can see will also be returned.
    """
    if isinstance(conv_ref, int):
        query = conns.main.fetchrow(
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
        query = conns.main.fetchrow(
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

    # TODO we should use a custom error here, not just 404: Conversation not found
    conv_id, publish_ts, creator, last_action = await or404(query, msg='Conversation not found')

    if not publish_ts and user_id != creator:
        raise JsonErrors.HTTPForbidden('conversation is unpublished and you are not the creator')
    if req_pub is not None and bool(publish_ts) != req_pub:
        msg = 'Conversation not yet published' if req_pub else 'Conversation already published'
        raise JsonErrors.HTTPBadRequest(msg)
    return conv_id, last_action


async def update_conv_users(conns: Connections, conv_id: int) -> List[int]:
    """
    Update v on users participating in a conversation
    """
    v = await conns.main.fetch(
        """
        update users set v=v + 1 from participants
        where participants.user_id = users.id and participants.conv = $1 and users.user_type = 'local'
        returning participants.user_id
        """,
        conv_id,
    )
    return [r[0] for r in v]


participant_action_types = {a for a in ActionTypes if a.value.startswith('participant:')}
_subject_action_types = {a for a in ActionTypes if a.value.startswith('subject:')}
_msg_action_types = {a for a in ActionTypes if a.value.startswith('message:')}
follow_action_types = (
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
    download_url: Optional[str] = None


@dataclass
class Action:
    act: ActionTypes
    actor_id: int
    id: Optional[int] = None
    ts: datetime = None
    body: str = None
    extra_body: bool = False
    participant: Optional[str] = None
    msg_format: MsgFormat = MsgFormat.markdown
    follows: Optional[int] = None
    parent: Optional[int] = None
    files: List[File] = None


class _Act:
    """
    See act() below for details.
    """

    __slots__ = 'conns', 'conv_id', 'new_user_ids', 'spam', 'warnings'

    def __init__(self, conns: Connections, spam: bool, warnings: Dict[str, str]):
        self.conns = conns
        self.conv_id = None
        # ugly way of doing this, but less ugly than other approaches
        self.new_user_ids: Set[int] = set()
        self.spam = True if spam else None
        self.warnings = json.dumps(warnings) if warnings else None  # FIXME moved to action

    async def prepare(self, conv_ref: StrInt, actor_id: int) -> Tuple[int, int, int]:
        self.conv_id, last_action = await get_conv_for_user(self.conns, actor_id, conv_ref)

        # we must be in a transaction
        # this is a hard check that conversations can only have one act applied at a time
        creator = await self.conns.main.fetchval(
            'select creator from conversations where id=$1 for no key update', self.conv_id
        )
        return last_action, self.conv_id, creator

    async def new_actor(self, actor_id: int):
        _, last_action = await get_conv_for_user(self.conns, actor_id, self.conv_id)
        return last_action

    async def run(self, action: Action, last_action: int) -> Tuple[Optional[int], Optional[int]]:
        if action.act is ActionTypes.seen:
            return await self._seen(action), None

        # you can mark a conversation as seen when removed, but nothing else
        if last_action:
            raise JsonErrors.HTTPBadRequest(message="You can't act on conversations you've been removed from")

        changed_user_id = None
        if action.act in participant_action_types:
            action_id, changed_user_id = await self._act_on_participant(action)
        elif action.act in _msg_action_types:
            action_id, action_pk = await self._act_on_message(action)
            if action.files:
                await create_files(self.conns, action.files, self.conv_id, action_pk)
        elif action.act in _subject_action_types:
            action_id = await self._act_on_subject(action)
        else:
            raise NotImplementedError

        return action_id, changed_user_id

    async def _seen(self, action: Action) -> Optional[int]:
        # could use "parent" to identify what was seen
        last_seen = await self.conns.main.fetchval(
            """
            select a.id from actions as a
            where a.conv=$1 and act='seen' and actor=$2
            order by id desc
            limit 1
            """,
            self.conv_id,
            action.actor_id,
        )
        if last_seen:
            last_real_action = await self.conns.main.fetchval(
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

        return await self.conns.main.fetchval(
            """
            insert into actions (conv, actor, act   )
            values              ($1  , $2   , 'seen')
            returning id
            """,
            self.conv_id,
            action.actor_id,
        )

    async def _act_on_participant(self, action: Action) -> Tuple[int, int]:
        follows_pk = None
        if action.act == ActionTypes.prt_add:
            prts_count = await self.conns.main.fetchval('select count(*) from participants where conv=$1', self.conv_id)
            if prts_count == max_participants:
                raise JsonErrors.HTTPBadRequest(f'no more than {max_participants} participants permitted')

            prt_user_id = await get_create_user(self.conns, action.participant)
            removed_prt_id = await self.conns.main.fetchval(
                'select id from participants where conv=$1 and user_id=$2 and removal_action_id is not null',
                self.conv_id,
                prt_user_id,
            )
            if removed_prt_id:
                prt_id = removed_prt_id
                await self.conns.main.execute(
                    """
                    update participants set removal_action_id=null, removal_details=null, removal_updated_ts=null
                    where id=$1
                    """,
                    prt_id,
                )
            else:
                prt_id = await self.conns.main.fetchval(
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
                prt_id, prt_user_id = await or400(
                    self.conns.main.fetchrow(
                        """
                        select p.id, u.id from participants as p join users as u on p.user_id = u.id
                        where conv=$1 and email=$2
                        """,
                        self.conv_id,
                        action.participant,
                    ),
                    msg='participant not found on conversation',
                )
            else:
                raise NotImplementedError('"participant:modify" not yet implemented')

        # can't do anything to yourself
        if prt_user_id == action.actor_id:
            raise JsonErrors.HTTPForbidden('You cannot modify your own participant')

        action_id = await self.conns.main.fetchval(
            """
            insert into actions (id, ts        , conv, act, actor, follows, participant_user)
            values              ($1, or_now($2), $3  , $4 , $5   , $6     , $7)
            returning id
            """,
            action.id,
            action.ts,
            self.conv_id,
            action.act,
            action.actor_id,
            follows_pk,
            prt_user_id,
        )
        if action.act == ActionTypes.prt_remove:
            await self.conns.main.execute(
                """
                update participants p set
                removal_action_id=$1, removal_details=c.details, removal_updated_ts=c.updated_ts
                from conversations c
                where p.id=$2 and p.conv=c.id
                """,
                action_id,
                prt_id,
            )
        return action_id, prt_user_id

    async def _act_on_message(self, action: Action) -> Tuple[int, int]:
        if action.act == ActionTypes.msg_add:
            parent_pk = None
            if action.parent:
                # just check tha parent really is an action on this conversation of type message:add
                parent_pk = await or404(
                    self.conns.main.fetchval(
                        "select pk from actions where conv=$1 and id=$2 and act='message:add'",
                        self.conv_id,
                        action.parent,
                    ),
                    msg='parent action not found',
                )
            # no extra checks required, you can add a message even after a deleted message, this avoids complex
            # checks that no message in the hierarchy has been deleted
            return await self.conns.main.fetchrow(
                """
                insert into actions
                        (id, ts       , conv, act          , actor, body, preview, parent, msg_format, warnings)
                values ($1, or_now($2), $3  , 'message:add', $4   , $5  , $6     , $7    , $8        , $9)
                returning id, pk
                """,
                action.id,
                action.ts,
                self.conv_id,
                action.actor_id,
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
            if follows_act != ActionTypes.msg_lock or follows_actor != action.actor_id:
                # TODO lock maybe shouldn't be required when conversation is draft
                raise JsonErrors.HTTPBadRequest(f'{action.act} must follow message:lock by the same user')
        else:
            # just lock and delete here
            if follows_act == ActionTypes.msg_delete:
                raise JsonErrors.HTTPBadRequest('only message:recover can occur on a deleted message')
            elif (
                follows_act == ActionTypes.msg_lock
                and follows_actor != action.actor_id
                and follows_age <= self.conns.settings.message_lock_duration
            ):
                details = {'loc_duration': self.conns.settings.message_lock_duration}
                raise JsonErrors.HTTPConflict('message locked, action not possible', details=details)

        return await self.conns.main.fetchrow(
            """
            insert into actions (id, ts        , conv, actor, act, body, preview, follows)
            values              ($1, or_now($2), $3  , $4   , $5 , $6  , $7     , $8)
            returning id, pk
            """,
            action.id,
            action.ts,
            self.conv_id,
            action.actor_id,
            action.act,
            action.body,
            message_preview(action.body, action.msg_format) if action.act == ActionTypes.msg_modify else None,
            follows_pk,
        )

    async def _act_on_subject(self, action: Action) -> int:
        follow_types = _subject_action_types | {ActionTypes.conv_create, ActionTypes.conv_publish}
        follows_pk, follows_act, follows_actor, follows_age = await self._get_follows(action, follow_types)

        if action.act == ActionTypes.subject_lock:
            if (
                follows_act == ActionTypes.subject_lock
                and follows_actor != action.actor_id
                and follows_age <= self.conns.settings.message_lock_duration
            ):
                details = {'loc_duration': self.conns.settings.message_lock_duration}
                raise JsonErrors.HTTPConflict('subject not locked by you, action not possible', details=details)
        else:
            # modify and release
            if follows_act != ActionTypes.subject_lock or follows_actor != action.actor_id:
                raise JsonErrors.HTTPBadRequest(f'{action.act} must follow subject:lock by the same user')

        return await self.conns.main.fetchval(
            """
            insert into actions (id, ts        , conv, actor, act, body, follows)
            values              ($1, or_now($2), $3  , $4   , $5 , $6  , $7)
            returning id
            """,
            action.id,
            action.ts,
            self.conv_id,
            action.actor_id,
            action.act,
            action.body,
            follows_pk,
        )

    async def _get_follows(self, action: Action, permitted_acts: Set[ActionTypes]) -> Tuple[int, str, int, int]:
        follows_pk, follows_act, follows_actor, follows_age = await or400(
            self.conns.main.fetchrow(
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
        existing = await self.conns.main.fetchrow(
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
    conns: Connections, conv_ref: StrInt, actions: List[Action], spam: bool = False, warnings: Dict[str, str] = None
) -> Tuple[int, List[int]]:
    """
    Apply actions and return their ids.

    Should be used for both remote platforms adding events and local users adding actions.
    """
    actions_with_ids: List[Tuple[int, Optional[int], Action]] = []
    act_cls = _Act(conns, spam, warnings)
    decrement_seen_id = None
    from_deleted, from_archive, already_inbox = [], [], []
    async with conns.main.transaction():
        # IMPORTANT must not do anything that could be slow (eg. networking) inside this transaction,
        # as the conv is locked for update from prepare onwards
        actor_user_id = actions[0].actor_id
        last_action, conv_id, creator_id = await act_cls.prepare(conv_ref, actor_user_id)

        for action in actions:
            if action.actor_id != actor_user_id:
                actor_user_id = action.actor_id
                last_action = await act_cls.new_actor(action.actor_id)
            action_id, changed_user_id = await act_cls.run(action, last_action)
            if action_id:
                actions_with_ids.append((action_id, changed_user_id, action))

    if actions_with_ids:
        # the actor is assumed to have seen the conversation as they've acted upon it
        v = await conns.main.execute(
            'update participants set seen=true where conv=$1 and user_id=$2 and seen is not true',
            conv_id,
            actor_user_id,
        )
        if v == 'UPDATE 1':
            # decrement unseen for the actor if we did mark the conversation as seen and it's in the inbox
            decrement_seen_id = await conns.main.fetchval(
                """
                select user_id from participants
                where conv=$1 and user_id=$2 and inbox is true and deleted is not true and spam is not true
                """,
                conv_id,
                actor_user_id,
            )
        # everyone else hasn't seen this action if it's "worth seeing"
        if any(a.act not in _meta_action_types for a in actions):
            from_deleted, from_archive, already_inbox = await user_flag_moves(conns, conv_id, actor_user_id)
        await update_conv_users(conns, conv_id)

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

    if decrement_seen_id:
        updates.append(UpdateFlag(decrement_seen_id, [(ConvFlags.unseen, -1)]))

    if updates:
        await update_conv_flags(conns, *updates)
    await search_update(conns, conv_id, actions_with_ids)
    return conv_id, [a[0] for a in actions_with_ids]


async def user_flag_moves(
    conns: Connections, conv_id: int, actor_user_id: int
) -> Tuple[List[int], List[int], List[int]]:
    # TODO we'll also need to exclude muted conversations from being moved, while still setting seen=false
    # we could exclude no local users from some of this
    return await conns.main.fetchrow(
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
    conns: Connections, user_id: int, conv_ref: StrInt, *, since_id: int = None, inc_seen: bool = False
):
    conv_id, last_action = await get_conv_for_user(conns, user_id, conv_ref)
    where_logic = V('a.conv') == conv_id
    if last_action:
        where_logic &= V('a.id') <= last_action

    if since_id:
        await or404(conns.main.fetchval('select 1 from actions where conv=$1 and id=$2', conv_id, since_id))
        where_logic &= V('a.id') > since_id

    if not inc_seen:
        where_logic &= V('a.act') != ActionTypes.seen

    return await or404(
        conns.main.fetchval_b(
            """
            select array_to_json(array_agg(json_strip_nulls(row_to_json(t))), true)
            from (
              select a.id, a.act, a.ts, actor_user.email actor,
              a.body, a.msg_format, a.warnings,
              prt_user.email participant, follows_action.id follows, parent_action.id parent,
              (select array_agg(row_to_json(f))
                from (
                  select storage, storage_expires, content_disp, hash, content_id, name, content_type, size
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


async def construct_conv(conns: Connections, user_id: int, conv_ref: StrInt, since_id: int = None):
    actions_json = await conv_actions_json(conns, user_id, conv_ref, since_id=since_id)
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
        actor: str = action['actor']
        if act in {ActionTypes.conv_publish, ActionTypes.conv_create}:
            subject = action['body']
            created = action['ts']
        elif act == ActionTypes.subject_modify:
            subject = action['body']
        elif act == ActionTypes.msg_add:
            # FIXME add actor to message
            d = {
                'ref': action_id,
                'author': actor,
                'body': action['body'],
                'created': action['ts'],
                'format': action['msg_format'],
                'parent': action.get('parent'),
                'active': True,
            }
            files = action.get('files')
            if files:
                d['files'] = files
            messages[action_id] = d
        elif act in _msg_action_types:
            message = messages[action['follows']]
            message['ref'] = action_id
            if act == ActionTypes.msg_modify:
                message['body'] = action['body']
                if 'editors' in message:
                    message['editors'].append(actor)
                else:
                    message['editors'] = [actor]
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


async def create_conv(  # noqa: 901
    *,
    conns: Connections,
    creator_email: str,
    actions: List[Action],
    given_conv_key: Optional[str] = None,
    leader_node: str = None,
    spam: bool = False,
    warnings: Dict[str, str] = None,
) -> Tuple[int, str]:
    """
    Create a new conversation, this is used:
    * locally when someone creates a conversation
    * upon receiving an SMTP message not associate with an existing conversation
    * upon receiving a new conversation view em2-push

    :param conns: connections to use when creating conversation
    :param creator_email: email address of user creating conversation
    :param actions: list of actions: add message, add participant, publish or create
    :param given_conv_key: given conversation key, checked to confirm it matches generated conv key if given
    :param leader_node: node of the leader of this conversation, black if this node
    :param spam: whether conversation is spam
    :param warnings: warnings about the conversation
    :return: tuple conversation id and key
    """
    main_action: Optional[Action] = None

    # lookup from email address of participants to IDs of the actions used when adding that prt
    participants: Dict[str, Optional[int]] = {}
    messages: List[Action] = []

    for action in actions:
        if action.act in {ActionTypes.conv_publish, ActionTypes.conv_create}:
            main_action = action
        elif action.act == ActionTypes.msg_add:
            messages.append(action)
        elif action.act == ActionTypes.prt_add:
            participants[action.participant] = action.id

    assert main_action is not None, 'no publish or create action found'
    ts = main_action.ts or utcnow()

    publish = main_action.act == ActionTypes.conv_publish
    creator_id = main_action.actor_id
    conv_key = generate_conv_key(creator_email, ts, main_action.body) if publish else draft_conv_key()
    if given_conv_key is not None and given_conv_key != conv_key:
        raise JsonErrors.HTTPBadRequest('invalid conversation key', details={'expected': conv_key})
    async with conns.main.transaction():
        conv_id = await conns.main.fetchval(
            """
            insert into conversations (key, creator, publish_ts, created_ts, updated_ts, leader_node)
            values                    ($1,  $2     , $3        , $4        , $4        , $5         )
            on conflict (key) do nothing
            returning id
            """,
            conv_key,
            creator_id,
            ts if publish else None,
            ts,
            leader_node,
        )
        if conv_id is None:
            raise JsonErrors.HTTPConflict(message='key conflicts with existing conversation')

        await conns.main.execute(
            'insert into participants (conv, user_id, seen, inbox) (select $1, $2, true, null)', conv_id, creator_id
        )
        if participants:
            part_users = await get_create_multiple_users(conns, participants.keys())
            other_user_emails, other_user_ids = zip(*part_users.items())
            await conns.main.execute(
                'insert into participants (conv, user_id, spam) (select $1, unnest($2::int[]), $3)',
                conv_id,
                other_user_ids,
                True if spam else None,
            )
            user_ids = [creator_id] + list(other_user_ids)
            action_ids = [1] + [participants[u_email] for u_email in other_user_emails]
        else:
            part_users = {}
            other_user_ids = []
            user_ids = [creator_id]
            action_ids = []
        await conns.main.execute(
            """
            insert into actions (conv, act              , actor, ts, participant_user , id) (
            select               $1  , 'participant:add', $2   , $3, unnest($4::int[]), unnest($5::int[])
            )
            """,
            conv_id,
            creator_id,
            ts,
            user_ids,
            action_ids,
        )
        warnings_ = json.dumps(warnings) if warnings else None
        values = [
            Values(
                conv=conv_id,
                id=m.id,
                act=ActionTypes.msg_add,
                actor=creator_id,
                ts=ts,
                body=m.body,
                preview=message_preview(m.body, m.msg_format),
                msg_format=m.msg_format,
                warnings=warnings_,
            )
            for m in messages
        ]
        msg_action_pks = await conns.main.fetch_b(
            'insert into actions (:values__names) values :values returning pk', values=MultipleValues(*values)
        )

        await conns.main.execute(
            """
            insert into actions (conv, act, actor, ts, body, id)
            values              ($1  , $2 , $3   , $4, $5  , $6)
            """,
            conv_id,
            main_action.act,
            creator_id,
            ts,
            main_action.body,
            main_action.id,
        )
        await update_conv_users(conns, conv_id)
        for r, m in zip(msg_action_pks, messages):
            action_pk = r[0]
            if m.files:
                await create_files(conns, m.files, conv_id, action_pk)
            if m.parent:
                await conns.main.execute(
                    """
                    update actions set parent=pk from
                      (select pk from actions where conv=$1 and id=$2) t
                    where conv=$1 and pk=$3
                    """,
                    conv_id,
                    m.parent,
                    action_pk,
                )

    if not publish:
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

    await update_conv_flags(conns, *updates)
    await search_create_conv(
        conns,
        conv_id=conv_id,
        creator_email=creator_email,
        creator_id=creator_id,
        users=part_users,
        subject=main_action.body,
        publish=publish,
        messages=messages,
    )
    return conv_id, conv_key


async def create_files(conns: Connections, files: List[File], conv_id: int, action_pk: int):
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
            download_url=f.download_url,
        )
        for f in files
    ]
    await conns.main.execute_b('insert into files (:values__names) values :values', values=MultipleValues(*values))


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


async def get_flag_counts(conns: Connections, user_id, *, force_update=False) -> dict:
    """
    Get counts for participant flags. Data is cached to a redis hash and retrieved from there if it exists.
    """
    flag_key = _flags_count_key(user_id)
    flags = await conns.redis.hgetall(flag_key)
    if flags and not force_update:
        flags = {k: int(v) for k, v in flags.items()}
    else:
        flags = dict(await conns.main.fetchrow(conv_flag_count_sql, user_id))
        tr = conns.redis.multi_exec()
        tr.hmset_dict(flag_key, flags)
        tr.expire(flag_key, 86400)
        await tr.execute()
    return flags


@dataclass
class UpdateFlag:
    user_id: int
    changes: Iterable[Tuple[ConvFlags, int]]


async def update_conv_flags(conns: Connections, *updates: UpdateFlag):
    """
    Increment or decrement counts for participant flags if they exist in the cache, also extends cache expiry.
    """

    async def update(u: UpdateFlag):
        key = _flags_count_key(u.user_id)
        if await conns.redis.exists(key):
            await asyncio.gather(
                conns.redis.expire(key, 86400), *(conns.redis.hincrby(key, c[0].value, c[1]) for c in u.changes if c)
            )

    await asyncio.gather(*(update(u) for u in updates if u))


def _label_count_key(user_id: int):
    return f'conv-counts-labels-{user_id}'


async def get_label_counts(conns: Connections, user_id: int) -> dict:
    """
    Get counts for labels. Data is cached to a redis hash and retrieved from there if it exists.
    """
    label_key = _label_count_key(user_id)
    labels = await conns.redis.hgetall(label_key)
    if labels:
        labels = {k: int(v) for k, v in labels.items()}
    else:
        labels = {str(k): v for k, v in await conns.main.fetch(conv_label_count_sql, user_id)}
        if labels:
            tr = conns.redis.multi_exec()
            tr.hmset_dict(label_key, labels)
            tr.expire(label_key, 86400)
            await tr.execute()
    return labels

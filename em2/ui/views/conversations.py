import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from atoolbox import JsonErrors, get_offset, json_response, parse_request_query, raw_json_response
from buildpg import MultipleValues, SetValues, V, Values, funcs
from pydantic import BaseModel, EmailStr, constr, validator

from em2.background import push_all, push_multiple
from em2.core import (
    Action,
    ActionTypes,
    ConvCreateMessage,
    ConvFlags,
    File,
    UpdateFlag,
    apply_actions,
    construct_conv,
    conv_actions_json,
    create_conv,
    follow_action_types,
    generate_conv_key,
    get_conv_for_user,
    get_flag_counts,
    get_label_counts,
    max_participants,
    participant_action_types,
    update_conv_flags,
    update_conv_users,
    with_body_actions,
)
from em2.search import search, search_publish_conv
from em2.utils.core import MsgFormat
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.storage import S3, StorageNotFound, parse_storage_uri

from .utils import ExecView, View, file_upload_cache_key


class ConvList(View):
    # FIXME we can remove counts
    sql = """
    select json_build_object(
      'conversations', conversations
    ) from (
      select coalesce(array_to_json(array_agg(row_to_json(t))), '[]') as conversations
      from (
        select c.key, c.created_ts,
          coalesce(p.removal_updated_ts, c.updated_ts) updated_ts,
          c.publish_ts,
          coalesce(p.removal_action_id, c.last_action_id) last_action_id,
          coalesce(p.removal_details, c.details) details,
          p.seen is true seen,
          (p.inbox is true and p.deleted is not true and p.spam is not true) inbox,
          (c.creator != p.user_id and p.inbox is not true and p.deleted is not true and p.spam is not true) archive,
          p.deleted is true deleted,
          p.removal_action_id is not null removed,
          p.spam is true spam,
          c.publish_ts is null draft,
          c.publish_ts is not null and c.creator = p.user_id sent,
          coalesce(p.label_ids, '{}') labels
        from conversations c
        join participants p on c.id = p.conv
        where :where
        order by c.updated_ts desc
        limit 50
        offset :offset
      ) t
    ) conversations
    """

    class QueryModel(BaseModel):
        flag: ConvFlags = None
        labels_all: List[int] = None
        labels_any: List[int] = None

    async def call(self):
        where = self.where_clause()
        raw_json = await self.conn.fetchval_b(self.sql, where=where, offset=get_offset(self.request, paginate_by=50))
        return raw_json_response(raw_json)

    def where_clause(self):
        # FIXME this doesn't get conversation where the user has been removed
        where = funcs.AND(
            V('p.user_id') == self.session.user_id,
            funcs.OR(V('publish_ts').is_not(V('null')), V('creator') == self.session.user_id),
        )

        query_data = parse_request_query(self.request, self.QueryModel)
        # SQL true
        true = V('true')
        # "is true" or "is not true" to work with null
        not_deleted = V('p.deleted').is_not(true)
        not_spam = V('p.spam').is_not(true)

        if query_data.flag is ConvFlags.inbox:
            where &= V('p.inbox').is_(true) & not_deleted & not_spam
        if query_data.flag is ConvFlags.unseen:
            where &= V('p.inbox').is_(true) & not_deleted & not_spam & V('p.seen').is_not(true)
        elif query_data.flag is ConvFlags.draft:
            where &= (V('c.creator') == V('p.user_id')) & V('c.publish_ts').is_(V('null')) & not_deleted
        elif query_data.flag is ConvFlags.sent:
            where &= (V('c.creator') == V('p.user_id')) & V('c.publish_ts').is_not(V('null')) & not_deleted
        elif query_data.flag is ConvFlags.archive:
            where &= (V('c.creator') != V('p.user_id')) & V('p.inbox').is_not(true) & not_deleted & not_spam
        elif query_data.flag is ConvFlags.spam:
            where &= V('p.spam').is_(true) & not_deleted
        elif query_data.flag is ConvFlags.deleted:
            where &= V('p.deleted').is_(true)

        if query_data.labels_all:
            where &= V('p.label_ids').contains(query_data.labels_all)
        elif query_data.labels_any:
            where &= V('p.label_ids').overlap(query_data.labels_any)

        return where


class ConvActions(View):
    class QueryModel(BaseModel):
        since: int = None

    async def call(self):
        m = parse_request_query(self.request, self.QueryModel)
        json_str = await conv_actions_json(
            self.conns, self.session.user_id, self.request.match_info['conv'], since_id=m.since, inc_seen=True
        )
        return raw_json_response(json_str)


class ConvDetails(View):
    sql = """
    select row_to_json(conversation)
    from (
      select c.key, c.created_ts,
        coalesce(p.removal_updated_ts, c.updated_ts) updated_ts,
        c.publish_ts,
        coalesce(p.removal_action_id, c.last_action_id) last_action_id,
        coalesce(p.removal_details, c.details) details,
        p.seen is true seen,
        (p.inbox is true and p.deleted is not true and p.spam is not true) inbox,
        (c.creator != p.user_id and p.inbox is not true and p.deleted is not true and p.spam is not true) archive,
        p.deleted is true deleted,
        p.removal_action_id is not null removed,
        p.spam is true spam,
        c.publish_ts is null draft,
        c.publish_ts is not null and c.creator = p.user_id sent,
        coalesce(p.label_ids, '{}') labels
      from conversations c
      join participants p on c.id = p.conv
      where c.key like $1 and p.user_id=$2
    ) conversation
    """

    async def call(self):
        json_str = await or404(
            self.conn.fetchval(self.sql, self.request.match_info['conv'] + '%', self.session.user_id),
            msg='Conversation not found',
        )
        return raw_json_response(json_str)


class ConvCreate(ExecView):
    class Model(BaseModel):
        subject: constr(max_length=255, strip_whitespace=True)
        message: constr(max_length=10000, strip_whitespace=True)
        msg_format: MsgFormat = MsgFormat.markdown
        publish = False

        class Participant(BaseModel):
            email: EmailStr
            name: str = None

        participants: List[Participant] = []

        @validator('participants', whole=True)
        def check_participants_count(cls, v):
            if len(v) > max_participants:
                raise ValueError(f'no more than {max_participants} participants permitted')
            return v

    async def execute(self, conv: Model):
        conv_id, conv_key = await create_conv(
            conns=self.conns,
            creator_email=self.session.email,
            creator_id=self.session.user_id,
            subject=conv.subject,
            publish=conv.publish,
            messages=[ConvCreateMessage(body=conv.message, msg_format=conv.msg_format)],
            participants={p.email: None for p in conv.participants},
        )

        await push_all(self.conns, conv_id)
        return dict(key=conv_key, status_=201)


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
        if act and not v and act in participant_action_types:
            raise ValueError('participant is required for participant actions')
        if act and v and act not in participant_action_types:
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
        if act and v is None and act in follow_action_types:
            raise ValueError('follows is required for this action')
        return v

    def as_raw_action(self, actor_id) -> Action:
        # technically unnecessary, could just cast
        return Action(actor_id=actor_id, **self.dict())


class ConvAct(ExecView):
    class Model(BaseModel):
        actions: List[ActionModel]
        files: List[str] = None

        @validator('files')
        def check_files(cls, value, values):
            actions: List[ActionModel] = values['actions']
            if len(actions) != 1 or actions[0].act != ActionTypes.msg_add:
                raise ValueError('files only valid with one "message:add" action')
            return value

    async def execute(self, m: Model):
        files = None
        if m.files:
            conv_id, _ = await get_conv_for_user(self.conns, self.session.user_id, self.request.match_info['conv'])
            files = await self.get_files(conv_id, m.files)
        conv_id, action_ids = await apply_actions(
            conns=self.conns,
            conv_ref=self.request.match_info['conv'],
            actions=[a.as_raw_action(self.session.user_id) for a in m.actions],
            files=files,
        )

        if action_ids:
            await push_multiple(self.conns, conv_id, action_ids)
        return {'action_ids': action_ids}

    async def get_files(self, conv_id: int, file_content_ids: List[str]) -> List[File]:
        async with S3(self.settings) as s3_client:
            return await asyncio.gather(
                *(self.prepare_file(s3_client, conv_id, content_id) for content_id in file_content_ids)
            )

    async def prepare_file(self, s3_client, conv_id, content_id: str):
        storage_path = await self.redis.get(file_upload_cache_key(conv_id, content_id))
        if not storage_path:
            raise JsonErrors.HTTPBadRequest(f'no file found for content id {content_id!r}')

        _, bucket, path = parse_storage_uri(storage_path)
        try:
            head = await s3_client.head(bucket, path)
        except StorageNotFound:
            raise JsonErrors.HTTPBadRequest('file not uploaded')
        else:
            return File(
                hash=head['ETag'].strip('"'),
                name=path.rsplit('/', 1)[1],
                content_id=content_id,
                content_disp='attachment' if 'ContentDisposition' in head else 'inline',
                content_type=head['ContentType'],
                size=head['ContentLength'],
                storage=storage_path,
            )


class ConvPublish(ExecView):
    class Model(BaseModel):
        publish: bool

        @validator('publish')
        def check_publish(cls, v):
            if not v:
                raise ValueError('publish must be true')
            return v

    async def execute(self, action: Model):
        conv_prefix = self.request.match_info['conv']
        conv_id, _ = await get_conv_for_user(self.conns, self.session.user_id, conv_prefix, req_pub=False)

        # could do more efficiently than this, but would require duplicate logic
        conv_summary = await construct_conv(self.conns, self.session.user_id, conv_prefix)
        old_key = await self.conns.main.fetchval('select key from conversations where id=$1', conv_id)

        ts = utcnow()
        conv_key = generate_conv_key(self.session.email, ts, conv_summary['subject'])
        async with self.conn.transaction():
            async with self.conn.transaction():
                # this is a hard check that conversations can't be published multiple times,
                # "for no key update" locks the row during this transaction
                publish_ts = await self.conn.fetchval(
                    'select publish_ts from conversations where id=$1 for no key update', conv_id
                )
                # this prevents a race condition if ConvPublish is called concurrently
                if publish_ts:
                    raise JsonErrors.HTTPBadRequest('Conversation already published')
                await self.conn.execute(
                    'update conversations set publish_ts=current_timestamp, last_action_id=0, key=$2 where id=$1',
                    conv_id,
                    conv_key,
                )

            # TODO, maybe in future we'll need a record of these old actions?
            await self.conn.execute('delete from actions where conv=$1', conv_id)

            await self.conn.execute(
                """
                insert into actions (conv, act, actor, ts, participant_user)
                (select $1, 'participant:add', $2, $3, user_id from participants where conv=$1)
                """,
                conv_id,
                self.session.user_id,
                ts,
            )
            files = []
            for msg in conv_summary['messages']:
                files += await self.add_msg(msg, conv_id, ts)

            if files:
                await self.conns.main.execute_b(
                    'insert into files (:values__names) values :values', values=MultipleValues(*files)
                )

            await self.conn.execute(
                """
                insert into actions (conv, act           , actor, ts, body)
                values              ($1  , 'conv:publish', $2   , $3, $4)
                """,
                conv_id,
                self.session.user_id,
                ts,
                conv_summary['subject'],
            )
            user_ids = await update_conv_users(self.conns, conv_id)

        other_user_ids = set(user_ids) - {self.session.user_id}
        updates = (
            UpdateFlag(self.session.user_id, [(ConvFlags.draft, -1), (ConvFlags.sent, 1)]),
            *(
                UpdateFlag(u_id, [(ConvFlags.inbox, 1), (ConvFlags.unseen, 1), (ConvFlags.all, 1)])
                for u_id in other_user_ids
            ),
        )
        await update_conv_flags(self.conns, *updates)
        await search_publish_conv(self.conns, conv_id, old_key, conv_key)
        await push_all(self.conns, conv_id)
        return dict(key=conv_key)

    async def add_msg(self, msg_info: Dict[str, Any], conv_id: int, ts: datetime, parent: int = None) -> List[Values]:
        """
        Recursively create messages.
        """
        pk = await self.conn.fetchval(
            """
            insert into actions (conv, act          , actor, ts, body, msg_format, parent)
            values              ($1  , 'message:add', $2   , $3, $4  , $5        , $6)
            returning pk
            """,
            conv_id,
            self.session.user_id,
            ts,
            msg_info['body'],
            msg_info['format'],
            parent,
        )
        files = [Values(conv=conv_id, action=pk, **f) for f in msg_info.get('files', [])]
        for msg in msg_info.get('children', []):
            files += await self.add_msg(msg, conv_id, ts, pk)
        return files


class SetFlags(str, Enum):
    archive = 'archive'
    inbox = 'inbox'
    delete = 'delete'
    restore = 'restore'
    spam = 'spam'
    ham = 'ham'


class SetConvFlag(View):
    class QueryModel(BaseModel):
        flag: SetFlags

    async def call(self):
        flag = parse_request_query(self.request, self.QueryModel).flag
        conv_id, _ = await get_conv_for_user(self.conns, self.session.user_id, self.request.match_info['conv'])
        async with self.conn.transaction():
            participant_id, inbox, seen, deleted, spam, self_created, draft = await self.conn.fetchrow(
                """
                select p.id, inbox, seen, deleted, spam, c.creator = $2, c.publish_ts is null
                from participants p
                join conversations c on p.conv = c.id
                where conv=$1 and user_id=$2 for no key update
                """,
                conv_id,
                self.session.user_id,
            )
            sent = self_created and not draft
            draft = self_created and draft

            values, changes = self.get_update_values(flag, inbox, seen, deleted, spam, sent, draft)
            await self.conn.execute_b('update participants set :values where id=:id', values=values, id=participant_id)
        await update_conv_flags(self.conns, UpdateFlag(self.session.user_id, changes))

        conv_flags = await self.conn.fetchrow(
            """
            select
              (inbox is true and deleted is not true and spam is not true) inbox,
              (inbox is not true and deleted is not true and spam is not true) archive,
              deleted is true deleted, spam is true spam
            from participants
            where id=$1
            """,
            participant_id,
        )
        counts = await get_flag_counts(self.conns, self.session.user_id)
        return json_response(conv_flags=dict(conv_flags), counts=counts)

    @staticmethod  # noqa: 901
    def get_update_values(
        flag: SetFlags, inbox: bool, seen: bool, deleted: bool, spam: bool, sent: bool, draft: bool
    ) -> Tuple[SetValues, list]:
        if flag is SetFlags.archive:
            if not inbox or deleted or spam or draft:
                raise JsonErrors.HTTPConflict('conversation not in inbox')

            if sent:
                changes = [(ConvFlags.inbox, -1), not seen and (ConvFlags.unseen, -1)]
            else:
                changes = [(ConvFlags.inbox, -1), (ConvFlags.archive, 1), not seen and (ConvFlags.unseen, -1)]

            return SetValues(inbox=None), changes
        elif flag is SetFlags.inbox:
            if deleted or spam or draft:
                raise JsonErrors.HTTPBadRequest('deleted, spam or draft conversation cannot be moved to inbox')
            elif inbox:
                raise JsonErrors.HTTPConflict('conversation already in inbox')

            if sent:
                changes = [(ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1)]
            else:
                changes = [(ConvFlags.archive, -1), (ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1)]

            return SetValues(inbox=True), changes
        elif flag is SetFlags.delete:
            if deleted:
                raise JsonErrors.HTTPConflict('conversation already deleted')

            if spam:
                changes = [(ConvFlags.spam, -1), (ConvFlags.deleted, 1)]
            elif inbox:
                changes = [(ConvFlags.inbox, -1), not seen and (ConvFlags.unseen, -1), (ConvFlags.deleted, 1)]
            elif draft:
                changes = [(ConvFlags.draft, -1), (ConvFlags.deleted, 1)]
            elif not sent:
                changes = [(ConvFlags.archive, -1), (ConvFlags.deleted, 1)]
            else:
                changes = [(ConvFlags.deleted, 1)]

            if sent:
                # like this because conversations can show in inbox and sent
                changes += [(ConvFlags.sent, -1)]

            return SetValues(deleted=True, deleted_ts=funcs.now()), changes
        elif flag is SetFlags.restore:
            if not deleted:
                raise JsonErrors.HTTPConflict('conversation not deleted')

            if spam:
                changes = [(ConvFlags.spam, 1), (ConvFlags.deleted, -1)]
            elif inbox:
                changes = [(ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1), (ConvFlags.deleted, -1)]
            elif draft:
                changes = [(ConvFlags.draft, 1), (ConvFlags.deleted, -1)]
            elif not sent:
                changes = [(ConvFlags.archive, 1), (ConvFlags.deleted, -1)]
            else:
                changes = [(ConvFlags.deleted, -1)]

            if sent:
                # like this because conversations can show in inbox and sent
                changes += [(ConvFlags.sent, 1)]

            return SetValues(deleted=None, deleted_ts=None), changes
        elif flag is SetFlags.spam:
            if spam:
                raise JsonErrors.HTTPConflict('conversation already spam')
            elif sent or draft:
                raise JsonErrors.HTTPBadRequest('you cannot spam your own conversations')

            if deleted:
                # deleted takes precedence over spam, so the conv is already "in deleted"
                changes = []
            elif inbox:
                changes = [(ConvFlags.inbox, -1), not seen and (ConvFlags.unseen, -1), (ConvFlags.spam, 1)]
            else:
                changes = [(ConvFlags.archive, -1), (ConvFlags.spam, 1)]

            return SetValues(spam=True), changes
        else:
            assert flag is SetFlags.ham, flag
            if not spam:
                raise JsonErrors.HTTPConflict('conversation not spam')

            if deleted:
                # deleted takes precedence over spam, so the conv is already "in deleted"
                changes = []
            elif inbox:
                changes = [(ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1), (ConvFlags.spam, -1)]
            else:
                changes = [(ConvFlags.archive, 1), (ConvFlags.spam, -1)]

            return SetValues(spam=None), changes


class GetConvCounts(View):
    class QueryModel(BaseModel):
        force_update: bool = False

    labels_sql = """
    select l.id, name, color, description
    from labels l
    left join participants p on label_ids @> array[l.id]
    where l.user_id = $1
    group by l.id
    order by l.ordering, l.id
    """

    async def call(self):
        force_update = parse_request_query(self.request, self.QueryModel).force_update
        flags = await get_flag_counts(self.conns, self.session.user_id, force_update=force_update)
        label_counts = await get_label_counts(self.conns, self.session.user_id)
        labels = [
            dict(id=r[0], name=r[1], color=r[2], description=r[3], count=label_counts[str(r[0])])
            for r in await self.conn.fetch(self.labels_sql, self.session.user_id)
        ]
        return json_response(flags=flags, labels=labels)


class Search(View):
    class QueryModel(BaseModel):
        query: str = ''

    async def call(self):
        query = parse_request_query(self.request, self.QueryModel).query
        ans = await search(self.conns, self.session.user_id, query)
        return raw_json_response(ans)

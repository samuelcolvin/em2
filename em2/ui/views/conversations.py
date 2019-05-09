from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Tuple

from aiohttp.web_exceptions import HTTPFound, HTTPNotImplemented
from atoolbox import JsonErrors, get_offset, json_response, parse_request_query, raw_json_response
from buildpg import SetValues, V, funcs
from pydantic import BaseModel, validator

from em2.background import push_all, push_multiple
from em2.core import (
    ActionModel,
    ConvFlags,
    CreateConvModel,
    UpdateFlag,
    apply_actions,
    construct_conv,
    conv_actions_json,
    create_conv,
    generate_conv_key,
    get_conv_counts,
    get_conv_for_user,
    update_conv_flags,
    update_conv_users,
)
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.smtp import CopyToTemp
from em2.utils.storage import S3, parse_storage_uri

from .utils import ExecView, View


class ConvList(View):
    # FIXME we can remove counts
    sql = """
    select json_build_object(
      'conversations', conversations
    ) from (
      select coalesce(array_to_json(array_agg(row_to_json(t))), '[]') as conversations
      from (
        select c.key, c.created_ts, c.updated_ts, c.publish_ts, c.last_action_id, c.details,
          p.seen is true seen,
          (p.inbox is true and p.deleted is not true and p.spam is not true) inbox,
          -- TODO (p.inbox is not true and p.deleted is not true and p.spam is not true) archive,
          p.deleted is true deleted,
          p.spam is true spam,
          c.publish_ts is null draft,
          c.publish_ts is not null and c.creator = p.user_id sent,
          coalesce(p.label_ids, '{}') labels
        from conversations c
        join participants p on c.id = p.conv
        where :where
        order by c.created_ts, c.id desc
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
            self.conn, self.session.user_id, self.request.match_info['conv'], since_id=m.since, inc_seen=True
        )
        return raw_json_response(json_str)


class ConvCreate(ExecView):
    Model = CreateConvModel

    async def execute(self, conv: CreateConvModel):
        conv_id, conv_key = await create_conv(
            conn=self.conn,
            redis=self.redis,
            creator_email=self.session.email,
            creator_id=self.session.user_id,
            conv=conv,
        )

        await push_all(self.conn, self.app['redis'], conv_id)
        return dict(key=conv_key, status_=201)


class ConvAct(ExecView):
    class Model(BaseModel):
        actions: List[ActionModel]

    async def execute(self, m: Model):
        conv_id, action_ids = await apply_actions(
            self.conn, self.redis, self.settings, self.session.user_id, self.request.match_info['conv'], m.actions
        )

        if action_ids:
            await push_multiple(self.conn, self.app['redis'], conv_id, action_ids)
        return {'action_ids': action_ids}


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
        conv_id, _ = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix, req_pub=False)

        # could do more efficiently than this, but would require duplicate logic
        conv_summary = await construct_conv(self.conn, self.session.user_id, conv_prefix)

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
            for msg in conv_summary['messages']:
                await self.add_msg(msg, conv_id, ts)

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
            await update_conv_users(self.conn, conv_id)
        await push_all(self.conn, self.app['redis'], conv_id)
        return dict(key=conv_key)

    async def add_msg(self, msg_info: Dict[str, Any], conv_id: int, ts: datetime, parent: int = None):
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
        for msg in msg_info.get('children', []):
            await self.add_msg(msg, conv_id, ts, pk)


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
        conv_id, _ = await get_conv_for_user(self.conn, self.session.user_id, self.request.match_info['conv'])
        async with self.conn.transaction():
            participant_id, inbox, seen, deleted, spam, self_created = await self.conn.fetchrow(
                """
                select p.id, inbox, seen, deleted, spam, c.creator = $2
                from participants p
                join conversations c on p.conv = c.id
                where conv=$1 and user_id=$2 for no key update
                """,
                conv_id,
                self.session.user_id,
            )
            if self_created:
                raise JsonErrors.HTTPBadRequest('you cannot change labels on conversations you sent')

            values, changes = self.get_update_values(flag, inbox, seen, deleted, spam)
            await self.conn.execute_b('update participants set :values where id=:id', values=values, id=participant_id)
        await update_conv_flags(UpdateFlag(self.session.user_id, filter(bool, changes)), redis=self.redis)

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
        flags_count, _ = await get_conv_counts(self.session.user_id, conn=self.conn, redis=self.redis)
        return json_response(conv=dict(conv_flags), counts=flags_count)

    @staticmethod  # noqa: 901
    def get_update_values(flag: SetFlags, inbox: bool, seen: bool, deleted: bool, spam: bool) -> Tuple[SetValues, list]:
        if flag is SetFlags.archive:
            if not (inbox and not deleted and not spam):
                raise JsonErrors.HTTPConflict('conversation not in inbox')
            changes = [(ConvFlags.inbox, -1), (ConvFlags.archive, 1), not seen and (ConvFlags.unseen, -1)]
            return SetValues(inbox=None), changes
        elif flag is SetFlags.inbox:
            if inbox:
                raise JsonErrors.HTTPConflict('conversation already in inbox')
            elif deleted or spam:
                raise JsonErrors.HTTPConflict('deleted or spam conversation cannot be moved to inbox')
            changes = [(ConvFlags.archive, -1), (ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1)]
            return SetValues(inbox=True), changes
        elif flag is SetFlags.delete:
            if deleted:
                raise JsonErrors.HTTPConflict('conversation already deleted')
            if inbox:
                changes = [(ConvFlags.inbox, -1), not seen and (ConvFlags.unseen, -1), (ConvFlags.deleted, 1)]
            elif spam:
                changes = [(ConvFlags.spam, -1), (ConvFlags.deleted, 1)]
            else:
                changes = [(ConvFlags.archive, -1), (ConvFlags.deleted, 1)]
            return SetValues(deleted=True, deleted_ts=funcs.now()), changes
        elif flag is SetFlags.restore:
            if not deleted:
                raise JsonErrors.HTTPConflict('conversation not deleted')
            if inbox:
                changes = [(ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1), (ConvFlags.deleted, -1)]
            elif spam:
                changes = [(ConvFlags.spam, 1), (ConvFlags.deleted, -1)]
            else:
                changes = [(ConvFlags.archive, 1), (ConvFlags.deleted, -1)]
            return SetValues(deleted=None, deleted_ts=None), changes
        elif flag is SetFlags.spam:
            if spam:
                raise JsonErrors.HTTPConflict('conversation already spam')
            if inbox:
                changes = [(ConvFlags.inbox, -1), not seen and (ConvFlags.unseen, -1), (ConvFlags.spam, 1)]
            elif deleted:
                changes = [(ConvFlags.spam, 1)]
            else:
                changes = [(ConvFlags.archive, -1), (ConvFlags.spam, 1)]
            return SetValues(spam=True), changes
        else:
            assert flag is SetFlags.ham, flag
            if not spam:
                raise JsonErrors.HTTPConflict('conversation not spam')
            if inbox:
                changes = [(ConvFlags.inbox, 1), not seen and (ConvFlags.unseen, 1), (ConvFlags.spam, -1)]
            elif deleted:
                changes = [(ConvFlags.spam, -1)]
            else:
                changes = [(ConvFlags.archive, 1), (ConvFlags.spam, -1)]
            return SetValues(spam=None), changes


class GetConvCounts(View):
    labels_sql = """
    select l.id, name, color, description
    from labels l
    left join participants p on label_ids @> array[l.id]
    where l.user_id = $1
    group by l.id
    order by l.ordering, l.id
    """

    async def call(self):
        flags, label_counts = await get_conv_counts(self.session.user_id, conn=self.conn, redis=self.redis)
        labels = [
            dict(id=r[0], name=r[1], color=r[2], description=r[3], count=label_counts[str(r[0])])
            for r in await self.conn.fetch(self.labels_sql, self.session.user_id)
        ]
        return json_response(flags=flags, labels=labels)


class GetFile(View):
    async def call(self):
        if not all((self.settings.aws_secret_key, self.settings.aws_access_key, self.settings.s3_temp_bucket)):
            raise HTTPNotImplemented(text="Storage keys not set, can't display images")
        # in theory we might need to add action_id here to specify the file via content_id, but in practice probably
        # not necessary (until it is)
        conv_prefix = self.request.match_info['conv']
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix)

        # order by f.id so that if some email system is dumb and repeats a content_id, we always use the first
        # one we received
        file_id, action_id, file_storage, storage_expires, send_id, send_storage = await or404(
            self.conn.fetchrow(
                """
                select f.id, a.id, f.storage, f.storage_expires, send, s.storage
                from files f
                join actions a on f.action = a.pk
                join sends s on a.pk = s.action
                where a.conv=$1 and f.content_id=$2
                order by f.id
                limit 1
                """,
                conv_id,
                self.request.match_info['content_id'],
            )
        )
        if last_action and action_id > last_action:
            raise JsonErrors.HTTPForbidden("You're not permitted to view this file")

        if file_storage and storage_expires > (utcnow() + timedelta(seconds=30)):
            storage_ref = file_storage
        else:
            storage_ref = await self.get_file_url(conv_id, send_id, file_id, send_storage)

        _, bucket, path = parse_storage_uri(storage_ref)
        url = S3(self.settings).sign_url(bucket, path)
        raise HTTPFound(url)

    async def get_file_url(self, conv_id: int, send_id: int, file_id: int, send_storage: str) -> str:
        await CopyToTemp(self.settings, self.conn, self.redis).run(conv_id, send_id, send_storage)

        storage = await self.conn.fetchval('select storage from files where id=$1', file_id)
        assert storage, 'storage still not set'
        return storage

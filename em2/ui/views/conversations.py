import asyncio
from datetime import datetime, timedelta
from mimetypes import guess_extension
from typing import Any, Dict, List, Optional

from aiohttp.web_exceptions import HTTPGatewayTimeout, HTTPTemporaryRedirect
from atoolbox import JsonErrors, get_offset, parse_request_query, raw_json_response
from pydantic import BaseModel, validator

from em2.background import push_all, push_multiple
from em2.core import (
    ActionModel,
    CreateConvModel,
    apply_actions,
    construct_conv,
    conv_actions_json,
    create_conv,
    generate_conv_key,
    get_conv_for_user,
    update_conv_users,
)
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.smtp import File, find_smtp_files, parse_smtp
from em2.utils.storage import S3, S3Client, parse_storage_uri

from .utils import ExecView, View


class ConvList(View):
    sql = """
    select json_build_object(
      'count', count,
      'conversations', conversations
    ) from (
      select count(*) from conversations as c
        join participants as p on c.id = p.conv
        where p.user_id=$1
        limit 999
    ) as count, (
      select coalesce(array_to_json(array_agg(row_to_json(t)), true), '[]') as conversations
      from (
        select key, created_ts, updated_ts, publish_ts, last_action_id, p.seen as seen, details
        from conversations as c
        join participants as p on c.id = p.conv
        where p.user_id=$1 and (publish_ts is not null or creator=$1)
        order by c.created_ts, c.id desc
        limit 50
        offset $2
      ) t
    ) as conversations
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id, get_offset(self.request, paginate_by=50))
        return raw_json_response(raw_json)


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
            conn=self.conn, creator_email=self.session.email, creator_id=self.session.user_id, conv=conv
        )

        await push_all(self.conn, self.app['redis'], conv_id)
        return dict(key=conv_key, status_=201)


class ConvAct(ExecView):
    class Model(BaseModel):
        actions: List[ActionModel]

    async def execute(self, m: Model):
        conv_id, action_ids = await apply_actions(
            self.conn, self.settings, self.session.user_id, self.request.match_info['conv'], m.actions
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


class GetFile(View):
    async def call(self):
        conv_prefix = self.request.match_info['conv']
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix)
        file_id = int(self.request.match_info['id'])
        action_id, storage, storage_expires, send_id, send_storage = await or404(
            self.conn.fetchrow(
                """
                select a.id, f.storage, f.storage_expires, send, s.storage
                from files f
                join actions a on f.action = a.pk
                join sends s on a.pk = s.action
                where f.id=$1 and a.conv=$2
                """,
                file_id,
                conv_id,
            )
        )
        if last_action and action_id > last_action:
            raise JsonErrors.HTTPForbidden('not permitted to view this file')

        storage_ref = await self.get_file_url(file_id, storage, storage_expires, send_id, send_storage, conv_id)
        _, bucket, path = parse_storage_uri(storage_ref)
        url = S3(self.settings).sign_url(bucket, path)
        raise HTTPTemporaryRedirect(url)

    async def get_file_url(
        self,
        file_id: int,
        storage: Optional[str],
        storage_expires: datetime,
        send_id: int,
        send_storage: str,
        conv_id: int,
    ) -> str:
        min_storage_expiry = utcnow() + timedelta(seconds=30)
        if storage and storage_expires < min_storage_expiry:
            return storage

        key = f'get-files:{send_id}'
        tr = self.redis.multi_exec()
        tr.incr(key)
        tr.expire(key, 60)
        ongoing, _ = await tr.execute()
        if ongoing:
            await self.await_ongoing(key)
        else:
            await self.update_storage(send_id, send_storage, conv_id, key)

        storage = await self.conn.fetchval('select storage from files where id=$1', file_id)
        assert storage, 'storage still not set'
        return storage

    async def await_ongoing(self, key):
        for i in range(20):
            if not await self.redis.exists(key):
                return
            await asyncio.sleep(0.5)

        raise HTTPGatewayTimeout(body=b'timeout waiting for s3 files to be prepared elsewhere')

    async def update_storage(self, send_id: int, send_storage: str, conv_id: int, cache_key: str):
        _, bucket, send_path = parse_storage_uri(send_storage)
        conv_key = self.conn.fetchval('select key from conversations where id=$1', conv_id)
        async with S3(self.settings) as s3_client:
            body = await s3_client.download(bucket, send_path)
            msg = parse_smtp(body)
            del body
            expires = utcnow() + timedelta(days=30)
            results = await asyncio.gather(
                *(self.upload_file(s3_client, conv_key, send_path, f) for f in find_smtp_files(msg, True))
            )
        for ref, storage in results:
            v = await self.conn.execute(
                'update files set storage=$1, storage_expires=$2 where send=$3 and ref=$4',
                storage,
                expires,
                send_id,
                ref,
            )
            assert v
            # debug(ref, storage, v)
        await self.redis.delete(cache_key)

    async def upload_file(self, s3_client: S3Client, conv_key, send_path, file: File):
        ct = file.content_type
        ext = guess_extension(ct)
        if ext is None:
            ct = None

        path = f'{conv_key}/{send_path}/{file.ref}.{ext}'
        bucket = self.settings.s3_temp_bucket
        await s3_client.upload(bucket, path, file.content, ct)
        return file.ref, f's3://{bucket}/{path}'

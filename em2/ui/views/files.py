import json
from datetime import timedelta
from uuid import uuid4

from aiohttp.web_exceptions import HTTPFound, HTTPNotImplemented
from atoolbox import JsonErrors, json_response, parse_request_query
from pydantic import BaseModel, conint, constr, validator

from em2.core import get_conv_for_user
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.smtp import CopyToTemp
from em2.utils.storage import S3, parse_storage_uri

from .utils import View, file_upload_cache_key


class GetFile(View):
    async def call(self):
        if not all((self.settings.aws_secret_key, self.settings.aws_access_key, self.settings.s3_temp_bucket)):
            raise HTTPNotImplemented(text="Storage keys not set, can't display images")
        # in theory we might need to add action_id here to specify the file via content_id, but in practice probably
        # not necessary (until it is)
        conv_prefix = self.request.match_info['conv']
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix)

        file_id, action_id, file_storage, storage_expires, send_id, send_storage = await or404(
            self.conn.fetchrow(
                """
                select f.id, a.id, f.storage, f.storage_expires, send, s.storage
                from files f
                join actions a on f.action = a.pk
                join sends s on a.pk = s.action
                where f.conv=$1 and f.content_id=$2
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
        url = S3(self.settings).signed_download_url(bucket, path)
        raise HTTPFound(url)

    async def get_file_url(self, conv_id: int, send_id: int, file_id: int, send_storage: str) -> str:
        await CopyToTemp(self.settings, self.conn, self.redis).run(conv_id, send_id, send_storage)

        storage = await self.conn.fetchval('select storage from files where id=$1', file_id)
        assert storage, 'storage still not set'
        return storage


upload_pending_ttl = 3600
main_content_types = {'application', 'audio', 'font', 'image', 'text', 'video'}


class UploadFile(View):
    class QueryModel(BaseModel):
        filename: constr(max_length=100)
        content_type: constr(max_length=20)
        # default to 1 GB, could change per use in future
        size: conint(le=1024 ** 3)

        @validator('content_type')
        def check_content_type(cls, v: str):
            v = v.lower().strip(' \r\n')
            parts = v.split('/')
            if len(parts) != 2 or parts[0] not in main_content_types:
                raise ValueError('invalid Content-Type')
            return v

    async def call(self):
        if not all((self.settings.aws_secret_key, self.settings.aws_access_key, self.settings.s3_file_bucket)):
            raise HTTPNotImplemented(text="Storage keys not set, can't upload files")

        conv_prefix = self.request.match_info['conv']
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix)
        if last_action:
            raise JsonErrors.HTTPForbidden()

        m = parse_request_query(self.request, self.QueryModel)
        conv_key = await self.conn.fetchval('select key from conversations where id=$1', conv_id)
        content_id = str(uuid4())

        bucket = self.settings.s3_file_bucket
        d = S3(self.settings).signed_upload_url(
            bucket=bucket,
            path=f'{conv_key}/{content_id}/',
            filename=m.filename,
            content_type=m.content_type,
            content_disp=True,
            size=m.size,
        )
        storage_path = 's3://{}/{}'.format(bucket, d['fields']['Key'])
        await self.redis.setex(file_upload_cache_key(conv_id, content_id), upload_pending_ttl, storage_path)
        await self.redis.enqueue_job(
            'delete_stale_upload', conv_id, content_id, storage_path, _defer_by=upload_pending_ttl
        )
        return json_response(content_id=content_id, **d)


async def delete_stale_upload(ctx, conv_id: int, content_id: str, storage_path: str):
    """
    Delete an uploaded file if it doesn't exist in the database.
    """
    file_exists = await ctx['pg'].fetchval('select 1 from files where conv=$1 and content_id=$2', conv_id, content_id)
    if file_exists:
        return
    _, bucket, path = parse_storage_uri(storage_path)
    async with S3(ctx['settings']) as s3_client:
        await s3_client.delete(bucket, path)
    return 1

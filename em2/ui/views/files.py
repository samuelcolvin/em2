import base64
from datetime import timedelta
from uuid import uuid4

from aiohttp.web_exceptions import HTTPFound, HTTPNotImplemented, HTTPOk
from atoolbox import JsonErrors, json_response, parse_request_query
from pydantic import BaseModel, conint, constr, validator

from em2.core import get_conv_for_user
from em2.settings import Settings
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.smtp import CopyToTemp
from em2.utils.storage import S3, check_content_type, file_upload_cache_key, parse_storage_uri

from .utils import View


class GetFile(View):
    async def call(self):
        s = self.settings
        if not all((s.aws_secret_key, s.aws_access_key, s.s3_temp_bucket)):  # pragma: no cover
            raise HTTPNotImplemented(text="Storage keys not set, can't display images")
        # in theory we might need to add action_id here to specify the file via content_id, but in practice probably
        # not necessary (until it is)
        conv_prefix = self.request.match_info['conv']
        c = await get_conv_for_user(self.conns, self.session.user_id, conv_prefix)

        file_id, action_id, file_storage, storage_expires, send_id, send_storage = await or404(
            self.conn.fetchrow(
                """
                select f.id, a.id, f.storage, f.storage_expires, send, s.storage
                from files f
                join actions a on f.action = a.pk
                left join sends s on f.send = s.id
                where f.conv=$1 and f.content_id=$2
                """,
                c.id,
                self.request.match_info['content_id'],
            ),
            msg='unable to find file',
        )
        if c.last_action and action_id > c.last_action:
            raise JsonErrors.HTTPForbidden("You're not permitted to view this file")

        if file_storage and (storage_expires is None or storage_expires > (utcnow() + timedelta(seconds=30))):
            storage_ref = file_storage
        else:
            assert send_storage, "send_storage should be set if file_storage isn't"
            storage_ref = await self.copy_to_temp(c.id, send_id, file_id, send_storage)

        _, bucket, path = parse_storage_uri(storage_ref)
        url = S3(s).signed_download_url(bucket, path)
        raise HTTPFound(url)

    async def copy_to_temp(self, conv_id: int, send_id: int, file_id: int, send_storage: str) -> str:
        await CopyToTemp(self.settings, self.conn, self.redis).run(conv_id, send_id, send_storage)

        storage = await self.conn.fetchval('select storage from files where id=$1', file_id)
        assert storage, 'storage still not set'
        return storage


class GetHtmlImage(View):
    async def call(self):
        s: Settings = self.settings
        if not all((s.aws_secret_key, s.aws_access_key, s.s3_cache_bucket)):  # pragma: no cover
            raise HTTPNotImplemented(text="Storage keys not set, can't display images")

        try:
            url = base64.b64decode(self.request.match_info['url']).decode()
        except ValueError:
            raise JsonErrors.HTTPBadRequest('invalid url')

        conv_prefix = self.request.match_info['conv']
        c = await get_conv_for_user(self.conns, self.session.user_id, conv_prefix)

        # does this query use indexes correctly?
        action_id, storage, error = await or404(
            self.conn.fetchrow(
                """
                update image_cache i set last_access=now()
                from actions a
                where i.conv=$1 and i.url=$2 and i.action = a.pk
                returning a.id, storage, error
                """,
                c.id,
                url,
            ),
            msg='unable to find image',
        )
        if c.last_action and action_id > c.last_action:
            raise JsonErrors.HTTPForbidden("You're not permitted to view this file")

        if error:
            # 200, but not an image should show image error in browser
            raise HTTPOk(text=f'unable to download image, {error}')

        _, bucket, path = parse_storage_uri(storage)
        url = S3(s).signed_download_url(bucket, path)
        raise HTTPFound(url)


class UploadFile(View):
    class QueryModel(BaseModel):
        filename: constr(max_length=100)
        content_type: constr(max_length=20)
        # default to 1 GB, could change per use in future
        size: conint(le=1024 ** 3)

        @validator('content_type')
        def check_content_type(cls, v: str):
            return check_content_type(v)

    async def call(self):
        s = self.settings
        if not all((s.aws_secret_key, s.aws_access_key, s.s3_file_bucket)):  # pragma: no cover
            raise HTTPNotImplemented(text="Storage keys not set, can't upload files")

        conv_prefix = self.request.match_info['conv']
        c = await get_conv_for_user(self.conns, self.session.user_id, conv_prefix)
        if c.last_action:
            raise JsonErrors.HTTPForbidden(message='file attachment not permitted')

        m = parse_request_query(self.request, self.QueryModel)
        content_id = str(uuid4())

        bucket = s.s3_file_bucket
        d = S3(s).signed_upload_url(
            bucket=bucket,
            path=f'{c.key}/{content_id}/',
            filename=m.filename,
            content_type=m.content_type,
            content_disp=True,
            size=m.size,
        )
        storage_path = 's3://{}/{}'.format(bucket, d['fields']['Key'])
        await self.redis.setex(file_upload_cache_key(c.id, content_id), self.settings.upload_pending_ttl, storage_path)
        await self.redis.enqueue_job(
            'delete_stale_upload', c.id, content_id, storage_path, _defer_by=self.settings.upload_pending_ttl
        )
        return json_response(file_id=content_id, **d)


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

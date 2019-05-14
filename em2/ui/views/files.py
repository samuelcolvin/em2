from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Tuple
from uuid import uuid4

from aiohttp.web_exceptions import HTTPFound, HTTPNotImplemented
from aiohttp.web_response import Response
from atoolbox import JsonErrors, get_offset, json_response, parse_request_query, raw_json_response
from buildpg import SetValues, V, funcs
from pydantic import BaseModel, constr, validator

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
    get_conv_for_user,
    get_flag_counts,
    get_label_counts,
    update_conv_flags,
    update_conv_users,
)
from em2.utils.datetime import utcnow
from em2.utils.db import or404
from em2.utils.smtp import CopyToTemp
from em2.utils.storage import S3, parse_storage_uri

from .utils import ExecView, View


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
        url = S3(self.settings).signed_download_url(bucket, path)
        raise HTTPFound(url)

    async def get_file_url(self, conv_id: int, send_id: int, file_id: int, send_storage: str) -> str:
        await CopyToTemp(self.settings, self.conn, self.redis).run(conv_id, send_id, send_storage)

        storage = await self.conn.fetchval('select storage from files where id=$1', file_id)
        assert storage, 'storage still not set'
        return storage


main_content_types = {'application', 'audio', 'font', 'image', 'text', 'video'}


class UploadFile(View):
    class QueryModel(BaseModel):
        content_type: constr(max_length=20)
        filename: constr(max_length=100)

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
        content_id = uuid4()

        d = S3(self.settings).signed_upload_url(
            path=f'{conv_key}/{content_id}/',
            filename=m.filename,
            content_type=m.content_type,
            content_disp=True,
            # default to 1 GiB
            max_size=1024 ** 3,
        )
        url = d.pop('url')
        inputs = '\n'.join(f"<input type='input' name='{k}' value='{v}' /><br />" for k, v in d.items())
        html = f"""
<form action="{url}" method="post" enctype="multipart/form-data">
  {inputs}
  <input type="file"  name="file" /> <br />

  <input type="submit" name="submit" value="Upload to Amazon S3" />
</form>
        """
        return Response(text=html, content_type='text/html')

import asyncio
import hashlib
import logging
from dataclasses import dataclass
from email import policy as email_policy
from email.message import EmailMessage
from email.parser import BytesParser
from typing import Generator, Optional

from aiohttp.web_exceptions import HTTPGatewayTimeout
from aioredis import Redis
from buildpg.asyncpg import BuildPgConnection

from em2.settings import Settings

from .datetime import utcnow
from .storage import S3, S3Client, parse_storage_uri

__all__ = ('parse_smtp', 'File', 'find_smtp_files')

logger = logging.getLogger('em2.utils.smtp')
email_parser = BytesParser(policy=email_policy.default)


def parse_smtp(body: bytes) -> EmailMessage:
    return email_parser.parsebytes(body)


@dataclass
class File:
    hash: str
    name: str
    content_id: str
    content_disp: str
    content_type: str
    content: Optional[bytes]


def find_smtp_files(m: EmailMessage, inc_content=False, *, _msg_id=None, _cids=None) -> Generator[File, None, None]:
    msg_id = _msg_id or m.get('Message-ID', '').strip('<> ')
    cids = _cids or set()
    for part in m.iter_parts():
        disposition = part.get_content_disposition()
        if disposition:
            # https://tools.ietf.org/html/rfc2392

            name = part.get_filename()
            content_type = part.get_content_type()

            content = part.get_content()
            if isinstance(content, str):
                content = content.encode()

            hash = hashlib.sha1(f'{name or ""}/{content_type or ""}/'.encode() + content).hexdigest()
            content_id = part['Content-ID']
            if content_id:
                content_id = content_id.strip('<>')
            else:
                content_id = hash

            if content_id in cids:
                logger.warning('msg %s, duplicate content_id: %r', msg_id, content_id)
                continue
            cids.add(content_id)

            yield File(
                hash,
                name,
                content_id,
                'inline' if disposition == 'inline' else 'attachment',
                content_type,
                content if inc_content else None,
            )
        else:
            yield from find_smtp_files(part, inc_content=inc_content, _msg_id=msg_id, _cids=cids)


class CopyToTemp:
    """
    Copy attachments from a message to temporary storage for download, viewing etc.
    """

    def __init__(self, settings: Settings, conn: BuildPgConnection, redis: Redis):
        self.settings = settings
        self.conn = conn
        self.redis = redis

    async def run(self, conv_id: int, send_id: int, send_storage: str):
        key = f'get-files:{send_id}'
        tr = self.redis.multi_exec()
        tr.incr(key)
        tr.expire(key, 60)
        ongoing, _ = await tr.execute()
        if ongoing > 1:
            await self._await_ongoing(key)
        else:
            try:
                await self._copy_files(conv_id, send_id, send_storage)
            finally:
                await self.redis.delete(key)

    async def _copy_files(self, conv_id: int, send_id: int, send_storage: str):
        _, bucket, send_path = parse_storage_uri(send_storage)
        conv_key = await self.conn.fetchval('select key from conversations where id=$1', conv_id)
        async with S3(self.settings) as s3_client:
            body = await s3_client.download(bucket, send_path)
            msg = parse_smtp(body)
            del body
            expires = utcnow() + self.settings.s3_tmp_bucket_lifetime
            results = await asyncio.gather(
                *(self._upload_file(s3_client, conv_key, send_path, f) for f in find_smtp_files(msg, True))
            )
        for content_id, storage in results:
            v = await self.conn.execute(
                'update files set storage=$1, storage_expires=$2 where send=$3 and content_id=$4',
                storage,
                expires,
                send_id,
                content_id,
            )
            assert v
            # debug(ref, storage, v)

    async def _upload_file(self, s3_client: S3Client, conv_key, send_path, file: File):
        path = f'{conv_key}/{send_path}/{file.content_id}/{file.name}'
        bucket = self.settings.s3_temp_bucket
        assert bucket, 's3_temp_bucket not set'
        content_disposition = file.content_disp
        if file.content_disp == 'attachment':
            content_disposition = f'attachment; filename="{file.name}"'
        await s3_client.upload(bucket, path, file.content, file.content_type, content_disposition)
        return file.content_id, f's3://{bucket}/{path}'

    async def _await_ongoing(self, key, sleep=0.5):
        for i in range(20):
            if not await self.redis.exists(key):
                return i
            await asyncio.sleep(sleep)

        raise HTTPGatewayTimeout(text='timeout waiting for s3 files to be prepared elsewhere')
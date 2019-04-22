import base64
import hashlib
import hmac
import re
from math import ceil
from typing import Optional
from urllib.parse import urlencode

import aiobotocore
from aiobotocore import AioSession
from aiobotocore.client import AioBaseClient

from em2.settings import Settings

from .datetime import to_unix_s, utcnow

__all__ = ('parse_storage_uri', 'S3Client', 'S3')

uri_re = re.compile(r'^(s3)://([^/]+)/(.+)$')


def parse_storage_uri(uri):
    m = uri_re.search(uri)
    if not m:
        raise RuntimeError(f'url not recognised: {uri!r}')
    service, bucket, path = m.groups()
    return service, bucket, path


class S3Client:
    __slots__ = ('_client',)

    def __init__(self, client):
        self._client: AioBaseClient = client

    async def download(self, bucket: str, path: str):
        r = await self._client.get_object(Bucket=bucket, Key=path)
        async with r['Body'] as stream:
            return await stream.read()

    async def upload(
        self, bucket: str, path: str, content: bytes, content_type: Optional[str], content_disposition: Optional[str]
    ):
        return await self._client.put_object(
            Bucket=bucket, Key=path, Body=content, ContentType=content_type, ContentDisposition=content_disposition
        )


class S3:
    __slots__ = '_settings', '_session', '_client'

    def __init__(self, settings: Settings):
        self._settings: Settings = settings
        self._session: Optional[AioSession] = None
        self._client: Optional[AioBaseClient] = None

    async def __aenter__(self) -> S3Client:
        assert self._client is None, 'client not None'
        if self._session is None:
            self._session = aiobotocore.get_session()
        self._client = self._session.create_client(
            's3',
            region_name=self._settings.aws_region,
            aws_access_key_id=self._settings.aws_access_key,
            aws_secret_access_key=self._settings.aws_secret_key,
            endpoint_url=self._settings.s3_endpoint_url,
        )
        await self._client.__aenter__()
        return S3Client(self._client)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._client.__aexit__(exc_type, exc_val, exc_tb)
        self._client = None

    def sign_url(self, bucket: str, path: str, *, ttl: int = 10000) -> str:
        """
        Sign a path to authenticate download.

        The url is valid for between 30 seconds and ttl + 30 seconds, this is because hte signature is rounded
        so a CDN can better cache the content.
        """
        assert not path.startswith('/'), 'path should not start with /'
        min_expires = to_unix_s(utcnow()) + 30
        expires = int(ceil(min_expires / ttl) * ttl)
        to_sign = f'GET\n\n\n{expires}\n /{bucket} /{path}'
        signature = base64.b64encode(
            hmac.new(self._settings.aws_secret_key.encode(), to_sign.encode(), hashlib.sha1).digest()
        )
        args = {'AWSAccessKeyId': self._settings.aws_access_key, 'Signature': signature, 'expires': expires}
        return f'https://{bucket}/{path}?{urlencode(args)}'

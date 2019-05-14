import base64
import hashlib
import hmac
import json
import re
from datetime import timedelta
from math import ceil
from typing import Dict, Optional
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

    def signed_download_url(self, bucket: str, path: str, *, ttl: int = 10000) -> str:
        """
        Sign a path to authenticate download.

        The url is valid for between 30 seconds and ttl + 30 seconds, this is because the signature is rounded
        so a CDN can better cache the content.

        https://docs.aws.amazon.com/AmazonS3/latest/dev/RESTAuthentication.html#RESTAuthenticationQueryStringAuth
        """
        assert not path.startswith('/'), 'path should not start with /'
        min_expires = to_unix_s(utcnow()) + 30
        expires = int(ceil(min_expires / ttl) * ttl)
        to_sign = f'GET\n\n\n{expires}\n/{bucket}/{path}'
        signature = self._signature(to_sign)
        args = {'AWSAccessKeyId': self._settings.aws_access_key, 'Signature': signature, 'Expires': expires}
        return f'https://{bucket}/{path}?{urlencode(args)}'

    def signed_upload_url(
        self, *, bucket: str, path: str, filename: str, content_type: str, content_disp: bool, max_size: int
    ) -> Dict[str, str]:
        """
        https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
        """
        assert path.endswith('/'), 'path must end with "/"'
        assert not path.startswith('/'), 'path must not start with "/"'
        key = path + filename
        policy = {
            'expiration': f'{utcnow() + timedelta(hours=1):%Y-%m-%dT%H:%M:%SZ}',
            'conditions': [
                {'bucket': bucket},
                {'key': key},
                {'Content-Type': content_type},
                ['content-length-range', 0, max_size],
            ],
        }

        result = {'Key': key, 'Content-Type': content_type, 'AWSAccessKeyId': self._settings.aws_access_key}
        if content_disp:
            disp = {'Content-Disposition': f'attachment; filename="{filename}"'}
            policy['conditions'].append(disp)
            result.update(disp)

        encoded_policy = base64.b64encode(json.dumps(policy).encode()).decode()
        return dict(
            url=f'https://s3.{self._settings.aws_region}.amazonaws.com/{bucket}',
            Policy=encoded_policy,
            Signature=self._signature(encoded_policy),
            **result,
        )

    def _signature(self, to_sign: str) -> str:
        s = hmac.new(self._settings.aws_secret_key.encode(), to_sign.encode(), hashlib.sha1).digest()
        return base64.b64encode(s).decode()

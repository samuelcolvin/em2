import base64
import hashlib
import hmac
import json
import logging
import re
from datetime import timedelta
from math import ceil
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import aiobotocore
from aiobotocore import AioSession
from aiobotocore.client import AioBaseClient
from aiohttp import ClientError, ClientResponse, ClientSession
from botocore.exceptions import ClientError as BotoClientError

from em2.settings import Settings

from .datetime import to_unix_s, utcnow

logger = logging.getLogger('em2.utils.storage')
__all__ = (
    'parse_storage_uri',
    'S3Client',
    'S3',
    'check_content_type',
    'DownloadError',
    'download_remote_file',
    'image_extensions',
)

uri_re = re.compile(r'^(s3)://([^/]+)/(.+)$')


def parse_storage_uri(uri):
    m = uri_re.search(uri)
    if not m:
        raise RuntimeError(f'url not recognised: {uri!r}')
    service, bucket, path = m.groups()
    return service, bucket, path


class StorageNotFound(RuntimeError):
    pass


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
        await self._client.put_object(
            Bucket=bucket, Key=path, Body=content, ContentType=content_type, ContentDisposition=content_disposition
        )
        return f's3://{bucket}/{path}'

    async def delete(self, bucket: str, path: str):
        return await self._client.delete_object(Bucket=bucket, Key=path)

    async def head(self, bucket: str, path: str):
        try:
            d = await self._client.head_object(Bucket=bucket, Key=path)
        except BotoClientError as exc:
            code = exc.response.get('Error', {}).get('Code', 'Unknown')
            if code == '404':
                raise StorageNotFound()
            else:
                raise
        d.pop('ResponseMetadata')
        return d


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
        self, *, bucket: str, path: str, filename: str, content_type: str, content_disp: bool, size: int
    ) -> Dict[str, Any]:
        """
        https://docs.aws.amazon.com/AmazonS3/latest/API/sigv4-post-example.html
        """
        assert path.endswith('/'), 'path must end with "/"'
        assert not path.startswith('/'), 'path must not start with "/"'
        key = path + filename
        policy = {
            'expiration': f'{utcnow() + timedelta(seconds=60):%Y-%m-%dT%H:%M:%SZ}',
            'conditions': [
                {'bucket': bucket},
                {'key': key},
                {'Content-Type': content_type},
                ['content-length-range', size, size],
            ],
        }

        fields = {'Key': key, 'Content-Type': content_type, 'AWSAccessKeyId': self._settings.aws_access_key}
        if content_disp:
            disp = {'Content-Disposition': f'attachment; filename="{filename}"'}
            policy['conditions'].append(disp)
            fields.update(disp)

        b64_policy = base64.b64encode(json.dumps(policy).encode()).decode()
        fields.update(Policy=b64_policy, Signature=self._signature(b64_policy))
        return dict(url=f'https://{bucket}/', fields=fields)

    def _signature(self, to_sign: str) -> str:
        s = hmac.new(self._settings.aws_secret_key.encode(), to_sign.encode(), hashlib.sha1).digest()
        return base64.b64encode(s).decode()


main_content_types = {'application', 'audio', 'font', 'image', 'text', 'video'}


def check_content_type(v: str) -> str:
    v = v.lower().strip(' \r\n')
    parts = v.split('/')
    if len(parts) != 2 or parts[0] not in main_content_types:
        raise ValueError('invalid Content-Type')
    return v


# https://en.wikipedia.org/wiki/Comparison_of_web_browsers#Image_format_support looking at chrome and firefox
image_extensions = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/svg+xml': 'svg',
    'image/tiff': 'tiff',
    'image/bmp': 'bmp',
    'image/vnd.microsoft.icon': 'ico',
    'image/webp': 'webp',
    'image/x-icon': 'ico',
    'image/x‑xbm': 'xbm',
}


class DownloadError(RuntimeError):
    def __init__(self, error: str):
        self.error = error


def _check_headers(
    response: ClientResponse, require_image: bool, full_url: str, max_size: int, expected_size: int
) -> str:
    content_type = response.headers.get('Content-Type', '').lower()
    if require_image:
        ext = image_extensions.get(content_type)
        if not ext:
            logger.warning('unknown image Content-Type %r, url: %r', content_type, full_url)
            raise DownloadError('content_type_not_image')
    else:
        parts = content_type.split('/')
        if len(parts) != 2 or parts[0] not in main_content_types:
            logger.warning('unknown Content-Type %r, url: %r', content_type, full_url)
            raise DownloadError('content_type_invalid')

    try:
        content_length = int(response.headers['Content-Length'])
    except (KeyError, ValueError):
        # missing Content-Length is okay
        return content_type

    if max_size and content_length > max_size:
        raise DownloadError('content_length_too_large')
    if expected_size and content_length != expected_size:
        raise DownloadError('content_length_not_expected')
    return content_type


async def download_remote_file(
    url: str, session: ClientSession, *, require_image: bool = False, max_size: int = None, expected_size: int = None
) -> Tuple[bytes, str]:
    full_url = 'http:' + url if url.startswith('//') else url
    try:
        async with session.get(full_url, allow_redirects=True) as r:
            if r.status != 200:
                raise DownloadError(f'response_{r.status}')

            content_type = _check_headers(r, require_image, full_url, max_size, expected_size)
            max_size_ = max_size or expected_size

            # TODO we should download to a temporary local file in chunks
            content, actual_size = b'', 0
            async for chunk in r.content.iter_chunked(16384):
                content += chunk
                actual_size += len(chunk)
                if actual_size > max_size_:
                    raise DownloadError('streamed_file_too_large')
    except (ClientError, OSError) as e:
        # could do more errors here
        logger.warning('error downloading file from %r %s: %s', full_url, e.__class__.__name__, e, exc_info=True)
        raise DownloadError('download_error')
    else:
        return content, content_type

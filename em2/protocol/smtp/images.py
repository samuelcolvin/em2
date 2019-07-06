import asyncio
import hashlib
import logging
from typing import Optional, Set

from aiohttp import ClientError, InvalidURL
from buildpg import Values

from em2.settings import Settings
from em2.utils.storage import S3

logger = logging.getLogger('em2.smtp')

__all__ = ['get_images']


async def get_images(ctx, conv_id: int, image_urls: Set[str]):
    to_get = []

    async with ctx['pg'].acquire() as conn:
        conv_key = await conn.fetchval('select key from conversations where id=$1', conv_id)
        for url in image_urls:
            r = await conn.fetchrow(
                """
                select conv=$2 this_conv, storage, error, created, url, hash, content_type, size
                from image_cache
                where url=$1 and error is null
                order by conv=$2 desc, created desc
                limit 1
                """,
                url,
                conv_id,
            )
            if r:
                if r['this_conv']:
                    # file already exists in the cache for this conversation, don't need to do anything
                    continue
                existing = {k: v for k, v in r.items() if k != 'this_conv'}
            else:
                existing = None

            to_get.append((url, existing))

    if not to_get:
        # nothing to do
        return

    settings: Settings = ctx['settings']
    session = ctx['client_session']
    to_create = await asyncio.gather(*[get_image(u, existing, conv_key, session, settings) for u, existing in to_get])

    async with ctx['pg'].acquire() as conn:
        for row in to_create:
            await conn.execute_b(
                'insert into image_cache (:values__names) values :values', values=Values(conv=conv_id, **row)
            )


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


async def get_image(url: str, existing: Optional[dict], conv_key: str, session, settings: Settings) -> dict:
    def _error(error: int) -> dict:
        return {'url': url, 'error': error, 'storage': None, 'size': None, 'hash': None, 'content_type': None}

    full_url = 'http:' + url if url.startswith('//') else url
    try:
        async with session.get(full_url, allow_redirects=True) as r:
            if r.status != 200:
                return _error(r.status)
            content_type = r.headers.get('Content-Type', '').lower()
            ext = image_extensions.get(content_type)
            if not ext:
                logger.warning('unknown image Content-Type %r, url: %r', content_type, full_url)
                return _error(1415)

            content, size = b'', 0
            async for chunk in r.content.iter_chunked(16384):
                content += chunk
                size += len(chunk)
                if size > settings.max_ref_image_size:
                    return _error(1413)
    except (ClientError, InvalidURL, OSError) as e:
        # could do more errors here
        logger.warning('error downloading image from %r %s: %s', full_url, e.__class__.__name__, e, exc_info=True)
        return _error(1502)

    # TODO resize large images
    content_hash = hashlib.sha256(content).hexdigest()

    if existing and content_hash == existing['hash']:
        # file is the same, no need to save just use the existing version
        return existing

    async with S3(settings) as s3_client:
        storage = await s3_client.upload(
            bucket=settings.s3_cache_bucket,
            path=f'{conv_key}/{hashlib.sha256(url.encode()).hexdigest()}.{ext}',
            content=content,
            content_type=content_type,
            content_disposition='inline',
        )

    return {
        'url': url,
        'error': None,
        'storage': storage,
        'size': size,
        'hash': content_hash,
        'content_type': content_type,
    }

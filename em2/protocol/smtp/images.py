import asyncio
import hashlib
import logging
from typing import Optional, Set

from aiohttp import ClientSession
from buildpg import Values

from em2.settings import Settings
from em2.utils.storage import S3, DownloadError, download_remote_file, image_extensions

logger = logging.getLogger('em2.smtp')

__all__ = ['get_images']


async def get_images(ctx, conv_id: int, action_pk: int, image_urls: Set[str]):
    settings: Settings = ctx['settings']
    if not all((settings.aws_secret_key, settings.aws_access_key, settings.s3_cache_bucket)):  # pragma: no cover
        return "Storage keys not set, can't download images"

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

    session: ClientSession = ctx['client_session']
    to_create = await asyncio.gather(*[get_image(u, existing, conv_key, session, settings) for u, existing in to_get])

    async with ctx['pg'].acquire() as conn:
        for row in to_create:
            await conn.execute_b(
                'insert into image_cache (:values__names) values :values',
                values=Values(conv=conv_id, action=action_pk, **row),
            )


async def get_image(
    url: str, existing: Optional[dict], conv_key: str, session: ClientSession, settings: Settings
) -> dict:
    try:
        content, ct = await download_remote_file(url, session, require_image=True, max_size=settings.max_ref_image_size)
    except DownloadError as e:
        return {'url': url, 'error': e.error, 'storage': None, 'size': None, 'hash': None, 'content_type': None}

    # TODO resize large images
    content_hash = hashlib.sha256(content).hexdigest()

    if existing and content_hash == existing['hash']:
        # file is the same, no need to save just use the existing version
        return existing

    async with S3(settings) as s3_client:
        storage = await s3_client.upload(
            bucket=settings.s3_cache_bucket,
            path=f'{conv_key}/{hashlib.sha256(url.encode()).hexdigest()}.{image_extensions[ct]}',
            content=content,
            content_type=ct,
            content_disposition='inline',
        )

    return {
        'url': url,
        'error': None,
        'storage': storage,
        'size': len(content),
        'hash': content_hash,
        'content_type': ct,
    }

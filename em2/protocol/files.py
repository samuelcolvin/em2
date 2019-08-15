import hashlib
import logging

from aiohttp import ClientSession
from arq import Retry
from asyncpg.pool import Pool

from em2.settings import Settings
from em2.utils.storage import S3, DownloadError, download_remote_file

logger = logging.getLogger('em2.files')


async def download_push_file(ctx, conv_id: int, content_id: str):
    session: ClientSession = ctx['client_session']
    settings: Settings = ctx['settings']
    pg: Pool = ctx['pg']

    file_id, conv_key, expected_hash, size, url, filename, content_disp, content_type = await pg.fetchrow(
        """
        select f.id, key, hash, size, download_url, name, content_disp, content_type
        from files f
        join conversations c on f.conv = c.id
        where f.conv=$1 and f.content_id=$2
        """,
        conv_id,
        content_id,
    )
    if size > settings.max_em2_file_size:
        await pg.execute('update files set error=$2 where id=$1', file_id, 'file_too_large')
        return

    try:
        content, _ = await download_remote_file(url, session, expected_size=size)
    except DownloadError as e:
        await pg.execute('update files set error=$2 where id=$1', file_id, e.error)
        raise Retry(30)  # TODO better back-off

    content_hash = hashlib.sha256(content).hexdigest()
    if content_hash != expected_hash:
        await pg.execute('update files set error=$2 where id=$1', file_id, 'hashes_conflict')
        return

    async with S3(settings) as s3_client:
        storage = await s3_client.upload(
            bucket=settings.s3_file_bucket,
            path=f'{conv_key}/{content_id}/{filename}',
            content=content,
            content_type=content_type,
            content_disposition=content_disp,
        )

    await pg.execute('update files set storage=$2 where id=$1', file_id, storage)

import asyncio
from typing import Type

import aiodns
from aiohttp import ClientSession, ClientTimeout
from arq import Worker
from buildpg import asyncpg
from pydantic.utils import import_string

from em2.protocol.fallback import BaseFallbackHandler, fallback_send
from em2.protocol.push import push_actions
from em2.settings import Settings
from em2.ui.views.files import delete_stale_upload


async def startup(ctx):
    settings: Settings = ctx.get('settings') or Settings()
    ctx.update(
        settings=settings,
        pg=await asyncpg.create_pool_b(dsn=settings.pg_dsn),
        session=ClientSession(timeout=ClientTimeout(total=10)),
        resolver=aiodns.DNSResolver(nameservers=['1.1.1.1', '1.0.0.1']),
    )
    fallback_handler_cls: Type[BaseFallbackHandler] = import_string(settings.fallback_handler)
    fallback_handler = fallback_handler_cls(ctx)
    await fallback_handler.startup()
    ctx['fallback_handler'] = fallback_handler


async def shutdown(ctx):
    await asyncio.gather(ctx['session'].close(), ctx['pg'].close(), ctx['fallback_handler'].shutdown())


functions = [fallback_send, push_actions, delete_stale_upload]
worker_settings = dict(functions=functions, on_startup=startup, on_shutdown=shutdown)


def run_worker(settings: Settings):
    worker = Worker(redis_settings=settings.redis_settings, **worker_settings)
    worker.run()

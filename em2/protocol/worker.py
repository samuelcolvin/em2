import asyncio
from typing import Type

import aiodns
from aiohttp import ClientSession, ClientTimeout
from buildpg import asyncpg
from pydantic.utils import import_string

from em2.settings import Settings

from .fallback import BaseFallbackHandler
from .push import fallback_send, push_actions


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


class WorkerSettings:
    functions = [push_actions, fallback_send]
    on_startup = startup
    on_shutdown = shutdown

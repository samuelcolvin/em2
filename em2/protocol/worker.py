import asyncio

import aiodns
from aiohttp import ClientSession, ClientTimeout
from buildpg import asyncpg

from em2.settings import Settings

from .push import push_actions

dns_ips = ['1.1.1.1', '1.0.0.1']


async def startup(ctx):
    settings: Settings = ctx.get('settings') or Settings()
    ctx.update(
        settings=settings,
        pg=await asyncpg.create_pool_b(dsn=settings.pg_dsn),
        session=ClientSession(timeout=ClientTimeout(total=10)),
        resolver=aiodns.DNSResolver(nameservers=dns_ips),
    )


async def shutdown(ctx):
    await asyncio.gather(ctx['session'].close(), ctx['pg'].close())


class WorkerSettings:
    functions = [push_actions]
    on_startup = startup
    on_shutdown = shutdown

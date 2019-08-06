import asyncio
from typing import Type

import nacl.encoding
import nacl.signing
from aiodns import DNSResolver
from aiohttp import ClientSession, ClientTimeout
from arq import Worker
from buildpg import asyncpg
from pydantic.utils import import_string

from em2.protocol.push import push_actions
from em2.protocol.smtp import BaseSmtpHandler, smtp_send
from em2.protocol.smtp.images import get_images
from em2.settings import Settings
from em2.ui.views.files import delete_stale_upload
from em2.utils.db import Connections
from em2.utils.web_push import web_push


async def startup(ctx):
    settings: Settings = ctx.get('settings') or Settings()
    ctx.update(
        settings=settings,
        pg=await asyncpg.create_pool_b(dsn=settings.pg_dsn),
        client_session=ClientSession(timeout=ClientTimeout(total=10)),
        resolver=DNSResolver(nameservers=['1.1.1.1', '1.0.0.1']),
        signing_key=nacl.signing.SigningKey(seed=settings.signing_secret_key, encoder=nacl.encoding.HexEncoder),
    )
    smtp_handler_cls: Type[BaseSmtpHandler] = import_string(settings.smtp_handler)
    smtp_handler = smtp_handler_cls(ctx)
    await smtp_handler.startup()
    ctx.update(smtp_handler=smtp_handler, conns=Connections(ctx['pg'], ctx['redis'], settings))


async def shutdown(ctx):
    await asyncio.gather(ctx['client_session'].close(), ctx['pg'].close(), ctx['smtp_handler'].shutdown())


functions = [smtp_send, push_actions, delete_stale_upload, web_push, get_images]
worker_settings = dict(functions=functions, on_startup=startup, on_shutdown=shutdown)


def run_worker(settings: Settings):  # pragma: no cover
    worker = Worker(redis_settings=settings.redis_settings, **worker_settings)
    worker.run()

from dataclasses import dataclass
from typing import Any, Awaitable

from arq import ArqRedis
from atoolbox import JsonErrors
from buildpg.asyncpg import BuildPgConnection

from em2.settings import Settings


async def or404(coro: Awaitable, *, msg: str = 'unable to find value') -> Any:
    """
    await a coroutine and raise 404 if it returns None, else return the value.

    Used for db fetch calls eg `a, b, c = await or404(conn.fetchrow(...))
    """
    ans = await coro
    if ans is None:
        raise JsonErrors.HTTPNotFound(msg)
    return ans


@dataclass
class Connections:
    main: BuildPgConnection
    redis: ArqRedis
    settings: Settings


def conns_from_request(request) -> Connections:
    return Connections(request['conn'], request.app['redis'], request.app['settings'])

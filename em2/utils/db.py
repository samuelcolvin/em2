from dataclasses import dataclass
from typing import Any, Awaitable, Type

from arq import ArqRedis
from atoolbox import JsonErrors
from buildpg.asyncpg import BuildPgConnection

from em2.settings import Settings


async def or404(coro: Awaitable, *, msg: str = 'unable to find value') -> Any:
    """
    await a coroutine and raise 404 if it returns None, else return the value.

    Used for db fetch calls eg `a, b, c = await or404(conn.fetchrow(...))
    """
    return await _or_error(coro, JsonErrors.HTTPNotFound, msg)


async def or400(coro: Awaitable, *, msg: str = 'unable to find value') -> Any:
    """
    await a coroutine and raise 400 if it returns None, else return the value.
    """
    return await _or_error(coro, JsonErrors.HTTPBadRequest, msg)


async def _or_error(coro: Awaitable, exc_type: Type[Exception], msg: str = 'unable to find value') -> Any:
    ans = await coro
    if ans is None:
        raise exc_type(msg)
    return ans


@dataclass
class Connections:
    main: BuildPgConnection
    redis: ArqRedis
    settings: Settings


def conns_from_request(request) -> Connections:
    return Connections(request['conn'], request.app['redis'], request.app['settings'])

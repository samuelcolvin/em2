from typing import Any, Awaitable

from atoolbox import JsonErrors


async def or404(coro: Awaitable, *, msg: str = 'unable to find value') -> Any:
    """
    await a coroutine and raise 404 if it returns None, else return the value.

    Used for db fetch calls eg `a, b, c = await or404(conn.fetchrow(...))
    """
    ans = await coro
    if ans is None:
        raise JsonErrors.HTTPNotFound(msg)
    return ans

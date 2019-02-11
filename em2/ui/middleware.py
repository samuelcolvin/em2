from aiohttp.web_middlewares import middleware
from aiohttp.web_urldispatcher import MatchInfoError
from aiohttp_session import get_session
from atoolbox import JsonErrors
from pydantic.dataclasses import dataclass

# views which don't require authentication

AUTH_WHITELIST = {'index', 'auth-token'}


@dataclass
class Session:
    user_id: int
    session_id: int
    email: str
    ts: int


async def load_session(request) -> Session:
    s = await get_session(request)
    if not s.get('user_id'):
        raise JsonErrors.HTTPUnauthorized('Authorisation required')
    return Session(**dict(s))
    # TODO check session.ts is not too old


@middleware
async def user_middleware(request, handler):
    if isinstance(request.match_info, MatchInfoError) or request.match_info.route.name in AUTH_WHITELIST:
        return await handler(request)
    request['session'] = await load_session(request)
    return await handler(request)

from aiohttp.web_middlewares import middleware
from aiohttp.web_urldispatcher import MatchInfoError
from aiohttp_session import get_session
from atoolbox import JsonErrors
from pydantic.dataclasses import dataclass

# views which don't require authentication

AUTH_WHITELIST = {'ui.index', 'ui.online', 'ui.websocket', 'ui.auth-token'}


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
    if request['view_name'] not in AUTH_WHITELIST and not isinstance(request.match_info, MatchInfoError):
        request['session'] = await load_session(request)
    return await handler(request)

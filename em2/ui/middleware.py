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


@middleware
async def user_middleware(request, handler):
    if isinstance(request.match_info, MatchInfoError) or request.match_info.route.name in AUTH_WHITELIST:
        return await handler(request)
    session_obj = await get_session(request)
    if not session_obj.get('user_id'):
        raise JsonErrors.HTTPUnauthorized('request not authorised')
    session = Session(**dict(session_obj))
    # TODO check session.ts is not too old
    request['session'] = session
    return await handler(request)

from time import time

from aiohttp.web_middlewares import middleware
from aiohttp.web_urldispatcher import MatchInfoError
from aiohttp_session import get_session
from atoolbox import JsonErrors, get_ip
from pydantic.dataclasses import dataclass

# views which don't require authentication
from em2.settings import Settings
from em2.utils.web import full_url, internal_request_headers

AUTH_WHITELIST = {'ui.index', 'ui.online', 'ui.websocket', 'ui.auth-token'}


@dataclass
class Session:
    user_id: int
    session_id: int
    email: str
    ts: int


def dead_session_key(session_id: int) -> str:
    return f'dead-session:{session_id}'


async def load_session(request) -> Session:
    session = await get_session(request)
    if not session.get('user_id'):
        raise JsonErrors.HTTPUnauthorized('Authorisation required')

    if await request.app['redis'].exists(dead_session_key(session['session_id'])):
        raise JsonErrors.HTTPForbidden('Session dead')

    settings: Settings = request.app['settings']
    if session['ts'] > int(time()) + settings.micro_session_duration:
        url = full_url(settings, 'auth', '/update-session/')
        data = {
            'session_id': session['session_id'],
            'ip': get_ip(request),
            'user_agent': request.headers.get('User-Agent'),
        }
        headers = internal_request_headers(settings)
        async with request.app['http_client'].post(url, raise_for_status=True, json=data, headers=headers) as r:
            data = await r.json()

        session['ts'] = data['ts']
    return Session(**dict(session))


@middleware
async def user_middleware(request, handler):
    if request['view_name'] not in AUTH_WHITELIST and not isinstance(request.match_info, MatchInfoError):
        request['session'] = await load_session(request)
    return await handler(request)

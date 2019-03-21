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


def session_event(request, session_id, **extra):
    return dict(session_id=session_id, ip=get_ip(request), user_agent=request.headers.get('User-Agent'), **extra)


async def finish_session(request, session_id, action):
    settings = request.app['settings']
    url = full_url(settings, 'auth', '/session/finish/')
    data = session_event(request, session_id, action=action)
    async with request.app['http_client'].post(url, json=data, headers=internal_request_headers(settings)) as r:
        pass

    if r.status == 400:
        raise JsonErrors.HTTPBadRequest('wrong session id')
    assert r.status == 200, r.status


async def load_session(request) -> Session:
    session = await get_session(request)
    if not session.get('user_id'):
        raise JsonErrors.HTTPUnauthorized('Authorisation required')

    if await request.app['redis'].exists(dead_session_key(session['session_id'])):
        raise JsonErrors.HTTPUnauthorized('Session dead')

    settings: Settings = request.app['settings']
    now = int(time())
    if session['ts'] >= now + settings.session_expiry:
        await finish_session(request, session['session_id'], 'expired')
        raise JsonErrors.HTTPUnauthorized('Session expired, authorisation required')
    elif session['ts'] >= now + settings.micro_session_duration:
        url = full_url(settings, 'auth', '/session/update/')
        data = session_event(request, session['session_id'])
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

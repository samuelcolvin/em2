from aiohttp_session import get_session, new_session
from atoolbox import ExecView, JsonErrors, decrypt_json, get_ip, json_response
from pydantic import BaseModel

from em2.core import UserTypes, get_create_user
from em2.ui.middleware import dead_session_key
from em2.utils.web import full_url, internal_request_headers


class AuthExchangeToken(ExecView):
    """
    Exchange a token from auth login to set the session cookie.
    """

    class Model(BaseModel):
        auth_token: bytes

    async def execute(self, m: Model):
        d = decrypt_json(self.app, m.auth_token, ttl=30)
        s = {
            'user_id': await get_create_user(self.conn, d['email'], UserTypes.local),
            'session_id': d['session_id'],
            'email': d['email'],
            'ts': d['ts'],
        }
        session = await new_session(self.request)
        session.update(s)


async def logout(request):
    """
    Finish the session with auth, clear the cookie and stop the session being used again.
    """
    settings = request.app['settings']
    session_id = request['session'].session_id

    url = full_url(settings, 'auth', '/logout/')
    data = {'session_id': session_id, 'ip': get_ip(request), 'user_agent': request.headers.get('User-Agent')}
    async with request.app['http_client'].post(url, json=data, headers=internal_request_headers(settings)) as r:
        pass

    if r.status == 400:
        raise JsonErrors.HTTPBadRequest('wrong session id')

    assert r.status == 200, r.status

    session = await get_session(request)
    session.invalidate()
    await request.app['redis'].setex(dead_session_key(session_id), settings.micro_session_duration + 60, b'1')
    return json_response(status='ok')

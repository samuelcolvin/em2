from aiohttp_session import get_session, new_session
from atoolbox import ExecView, JsonErrors, decrypt_json, json_response
from pydantic import BaseModel

from em2.core import UserTypes, get_create_user
from em2.utils.web import full_url, session_event


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
    Finish the session with auth, clear the cookie and stop the session being used again
    """
    event, _ = session_event(request, 'logout')
    url = full_url(request.app['settings'], 'auth', '/logout/')
    data = {'session_id': request['session'].session_id, 'event': event}
    async with request.app['http_client'].post(url, json=data) as r:
        pass

    if r.status == 400:
        raise JsonErrors.HTTPBadRequest('wrong session id')

    session = await get_session(request)
    session.invalidate()
    return json_response(status='ok')

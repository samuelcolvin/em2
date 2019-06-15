from aiohttp_session import get_session
from atoolbox import ExecView, decrypt_json, json_response
from pydantic import BaseModel

from em2.core import UserTypes, get_create_user
from em2.ui.middleware import dead_session_key, finish_session
from em2.utils.db import conns_from_request


class AuthExchangeToken(ExecView):
    """
    Exchange a token from auth login to set the session cookie.
    """

    class Model(BaseModel):
        auth_token: bytes

    async def execute(self, m: Model):
        d = decrypt_json(self.app, m.auth_token, ttl=30)
        session = await get_session(self.request)
        user_id = await get_create_user(conns_from_request(self.request), d['email'], UserTypes.local)
        session[d['session_id']] = {'user_id': user_id, 'email': d['email'], 'ts': d['ts']}
        return {'user_id': user_id}


async def logout(request):
    """
    Finish the session with auth, clear the cookie and stop the session being used again.
    """
    session_id = request['session'].session_id
    await finish_session(request, session_id, 'logout')

    session = await get_session(request)
    session.pop(str(session_id))
    await request.app['redis'].setex(
        dead_session_key(session_id), request.app['settings'].micro_session_duration + 60, b'1'
    )
    return json_response(status='ok')


async def auth_check(request):
    """
    No-op view to set the session cookie, this is used by websocket since the "Set-Cookie" header
    doesn't work with 101 upgrade
    """
    return json_response(status='ok')

from aiohttp_session import new_session
from atoolbox import decrypt_json
from pydantic import BaseModel

from em2.core import get_create_user
from em2.utils.web import ExecView


class AuthExchangeToken(ExecView):
    """
    Exchange a token from auth login to set the session cookie.
    """

    class Model(BaseModel):
        auth_token: bytes

    async def execute(self, m: Model):
        d = decrypt_json(self.app, m.auth_token, ttl=30)
        s = {
            'user_id': await get_create_user(self.conn, d['email']),
            'session_id': d['session_id'],
            'email': d['email'],
            'ts': d['ts'],
        }
        session = await new_session(self.request)
        session.update(s)

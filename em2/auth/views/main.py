import json
import logging
from time import time

import bcrypt
from atoolbox import ExecView, encrypt_json, get_ip, json_response
from atoolbox.auth import check_grecaptcha
from atoolbox.utils import JsonErrors
from pydantic import BaseModel, EmailStr, constr

logger = logging.getLogger('em2.auth')


def session_event(request, ts, action_type):
    return json.dumps(
        {
            'ip': get_ip(request),
            'ts': ts,
            'ua': request.headers.get('User-Agent'),
            'ac': action_type,
            # TODO include info about which session this is when multiple sessions are active
        }
    )


create_session_sql = 'INSERT INTO auth_sessions (auth_user, events) VALUES ($1, ARRAY[$2::JSONB]) RETURNING id'


async def login_successful(request, user):
    ts = int(time())
    event = session_event(request, ts, 'login-pw')
    session_id = await request['conn'].fetchval(create_session_sql, user['id'], event)
    session = {
        'session_id': session_id,
        'name': '{first_name} {last_name}'.format(**user).strip(' '),
        'email': user['email'],
    }
    auth_token = encrypt_json(request.app, {'ts': ts, **session})
    return dict(auth_token=auth_token, session=session)


class Login(ExecView):
    get_user_sql = """
    SELECT id, first_name, last_name, email, password_hash
    FROM auth_users
    WHERE email=$1 AND account_status='active'
    """

    class Model(BaseModel):
        email: EmailStr
        password: constr(min_length=6, max_length=100)
        grecaptcha_token: str = None

    async def get(self):
        repeat_cache_key, _ = self._get_repeat_cache_key()
        v = await self.redis.get(repeat_cache_key)
        return json_response(grecaptcha_required=int(v or 0) >= self.settings.easy_login_attempts)

    async def execute(self, m: Model):
        repeat_cache_key, ip = self._get_repeat_cache_key()
        tr = self.redis.multi_exec()
        tr.incr(repeat_cache_key)
        tr.expire(repeat_cache_key, 60)
        login_attempted, _ = await tr.execute()

        if login_attempted > self.settings.max_login_attempts:
            logger.warning('%d login attempts from %s', login_attempted, ip)
            raise JsonErrors.HTTPBadRequest('max login attempts exceeded')
        elif login_attempted > self.settings.easy_login_attempts:
            logger.info('%d login attempts from %s', login_attempted, ip)
            await check_grecaptcha(m, self.request)

        if m.password == self.settings.dummy_password:
            return JsonErrors.HTTPBadRequest(message='password not allowed')

        user = await self.conn.fetchrow(self.get_user_sql, m.email)
        # always try hashing regardless of whether the user exists or has a password set to avoid timing attack
        user = user or dict(password_hash=None)
        password_hash = user['password_hash'] or self.app['dummy_password_hash']

        if bcrypt.checkpw(m.password.encode(), password_hash.encode()):
            return await login_successful(self.request, user)
        else:
            raise JsonErrors.HTTP470(
                message='invalid username or password',
                details={'grecaptcha_required': login_attempted >= self.settings.easy_login_attempts},
            )

    def _get_repeat_cache_key(self):
        ip = get_ip(self.request)
        return f'login-attempt:{ip}', ip

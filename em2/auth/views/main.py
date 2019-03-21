import logging

import bcrypt
from aiohttp.web_response import Response
from atoolbox import ExecView, encrypt_json, get_ip, json_response
from atoolbox.auth import check_grecaptcha
from atoolbox.utils import JsonErrors
from pydantic import BaseModel, EmailStr, constr

from em2.utils.web import internal_request_check, session_event

logger = logging.getLogger('em2.auth')


create_session_sql = 'insert into auth_sessions (user_id, events) values ($1, array[$2::json]) returning id'


async def login_successful(request, user):
    event, ts = session_event(request, 'login-pw')
    session_id = await request['conn'].fetchval(create_session_sql, user['id'], event)
    session = {
        'ts': ts,
        'session_id': session_id,
        'name': '{first_name} {last_name}'.format(**user).strip(' '),
        'email': user['email'],
    }
    # TODO include information about which ui node to connect to when we support multiple
    return dict(auth_token=encrypt_json(request.app, session), session=session)


class Login(ExecView):
    headers = {'Access-Control-Allow-Origin': 'null'}

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

        user = await self.conn.fetchrow(
            """
            select id, first_name, last_name, email, password_hash
            from auth_users
            where email=$1 and account_status='active'
            """,
            m.email,
        )
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


class Logout(ExecView):
    class Model(BaseModel):
        session_id: int
        event: str

    async def check_permissions(self):
        internal_request_check(self.request)

    async def execute(self, m: Model):
        v = await self.conn.execute(
            """
            update auth_sessions
            set active=false, last_active=now(), events=events || $1::json
            where id=$2 and active=true
            """,
            m.event,
            m.session_id,
        )
        if v != 'UPDATE 1':
            raise JsonErrors.HTTPBadRequest(f'wrong session id: {v!r}')


async def check_address(request):
    internal_request_check(request)
    email = await request.text()
    found = await request['conn'].fetchval('select 1 from auth_users where email=$1', email)
    return Response(body=b'1' if found else b'0')

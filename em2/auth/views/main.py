import logging
from enum import Enum
from typing import Optional

import bcrypt
from aiohttp.web_response import Response
from atoolbox import ExecView, encrypt_json, get_ip, json_response
from atoolbox.auth import check_grecaptcha
from atoolbox.utils import JsonErrors
from buildpg import V
from pydantic import BaseModel, EmailStr, IPvAnyAddress, constr

from em2.utils.web import internal_request_check, this_em2_node

logger = logging.getLogger('em2.auth')


async def em2_route(request):
    """
    Currently no logic here, just always use the only em2 protocol node.
    """
    return json_response(node=this_em2_node(request.app['settings']))


async def login_successful(request, user):
    session_id, ts = await request['conn'].fetchrow(
        """
        with s as (
          insert into auth_sessions (user_id) values ($1)
          returning id, started
        ), ua as (
          insert into auth_user_agents (value) values (coalesce($2, ''))
          on conflict (value) do update set _dummy=null
          returning id
        ), e as (
          insert into auth_session_events (session, action, ip, user_agent)
          select s.id, 'login-pw', $3, ua.id
          from s, ua
        )
        select s.id, extract(epoch from s.started)::int from s
        """,
        user['id'],
        request.headers.get('User-Agent'),
        get_ip(request),
    )
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


class UpdateSession(ExecView):
    class Model(BaseModel):
        session_id: int
        ip: str
        user_agent: Optional[str]

    async def check_permissions(self):
        internal_request_check(self.request)

    async def execute(self, m: Model):
        ts = await self.conn.fetchval(
            """
            with s as (
              update auth_sessions set last_active=now() where id=$1 and active=true
              returning id
            ), ua as (
              insert into auth_user_agents (value) values (coalesce($2, ''))
              on conflict (value) do update set _dummy=null
              returning id
            )
            insert into auth_session_events (session, action, ip, user_agent)
            select s.id, 'update', $3, ua.id from s, ua
            returning extract(epoch from ts)::int
            """,
            m.session_id,
            m.user_agent,
            m.ip,
        )
        if ts:
            return {'ts': ts}
        else:
            raise JsonErrors.HTTPBadRequest('wrong session id')


class FinishActions(str, Enum):
    logout = 'logout'
    expired = 'expired'
    expired_hard = 'expired-hard'


class FinishSession(ExecView):
    class Model(BaseModel):
        session_id: int
        ip: IPvAnyAddress
        user_agent: Optional[str]
        action: FinishActions

    async def check_permissions(self):
        internal_request_check(self.request)

    async def execute(self, m: Model):
        where = V('id') == m.session_id
        if m.action == FinishActions.logout:
            where &= V('active') == V('true')

        ts = await self.conn.fetchval_b(
            """
            with s as (
              update auth_sessions set active=false, last_active=now() where :where
              returning id
            ), ua as (
              insert into auth_user_agents (value) values (coalesce(:user_agent, ''))
              on conflict (value) do update set _dummy=null
              returning id
            )
            insert into auth_session_events (session, action, ip, user_agent)
            select s.id, :action, :ip, ua.id from s, ua
            returning ts
            """,
            where=where,
            action=m.action,
            ip=m.ip,
            user_agent=m.user_agent,
        )
        if not ts:
            raise JsonErrors.HTTPBadRequest('wrong session id')


async def check_address(request):
    internal_request_check(request)
    email = await request.text()
    found = await request['conn'].fetchval('select 1 from auth_users where email=$1', email)
    return Response(body=b'1' if found else b'0')

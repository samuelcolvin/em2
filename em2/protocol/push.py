import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Type
from urllib.parse import urlencode

import aiodns
from aiohttp import ClientConnectionError, ClientError, ClientSession
from arq import ArqRedis
from async_timeout import timeout
from asyncpg.pool import Pool
from atoolbox.json_tools import lenient_json
from cryptography.fernet import Fernet
from pydantic import BaseModel, UrlStr

from em2.core import ActionTypes, UserTypes
from em2.settings import Settings
from em2.utils.web import full_url, internal_request_headers

logger = logging.getLogger('em2.push')
# could try another subdomain with a random part incase people are using em2-platform
em2_subdomain = 'em2-platform'
RETRY = 'RT'
SMTP = 'SMTP'


class HttpError(RuntimeError):
    pass


@dataclass
class ResponseSummary:
    status: int
    headers: Dict[str, str]
    data: Any
    model: Optional[BaseModel]


class RouteModel(BaseModel):
    node: UrlStr


async def push_actions(ctx, actions_data: str, users: List[Tuple[str, UserTypes]]):
    pusher = Pusher(ctx)
    return await pusher.split_destinations(actions_data, users)


class Pusher:
    __slots__ = 'settings', 'job_try', 'auth_fernet', 'session', 'pg', 'resolver', 'redis', 'pg', 'local_check_url'

    def __init__(self, ctx):
        self.settings: Settings = ctx['settings']
        self.job_try = ctx['job_try']
        self.auth_fernet = Fernet(self.settings.auth_key)
        self.session: ClientSession = ctx['session']
        self.pg: Pool = ctx['pg']
        self.resolver: aiodns.DNSResolver = ctx['resolver']
        self.redis: ArqRedis = ctx['redis']
        self.local_check_url = full_url(self.settings, 'auth', '/check/')

    async def split_destinations(self, actions_data: str, users: List[Tuple[str, UserTypes]]):
        results = await asyncio.gather(*[self.resolve_user(*u) for u in users])
        retry_users, smtp, em2 = set(), set(), set()
        for node, email in filter(None, results):
            if node == RETRY:
                retry_users.add((email, False))
            elif node == SMTP:
                smtp.add(email)
            else:
                em2.add(node)

        if retry_users:
            await self.redis.enqueue_job(
                'push_actions', actions_data, retry_users, _job_try=self.job_try + 1, _defer_by=self.job_try * 10
            )
        actions = json.loads(actions_data)['actions']
        if smtp:
            logger.info('%d smtp emails to send', len(smtp))
            # "seen" actions don't get sent via SMTP
            # TODO anything else to skip here?
            if not all(a['act'] == ActionTypes.seen for a in actions):
                await self.redis.enqueue_job('smtp_send', actions)
        else:
            logger.info('%d em2 nodes to push action to', len(em2))
            raise NotImplementedError('pushing to other em2 platforms not yet supported')
        return f'retry={len(retry_users)} smtp={len(smtp)} em2={len(em2)}'

    async def resolve_user(self, email: str, current_user_type: UserTypes):
        if current_user_type == UserTypes.new:
            # only new users are checked to see if they're local
            h = internal_request_headers(self.settings)
            async with self.session.get(self.local_check_url, data=email, raise_for_status=True, headers=h) as r:
                content = await r.read()

            if content == b'1':
                # local user
                await self.pg.execute("update users set user_type='local' where email=$1", email)
                return

        user_node_key = f'user-node:{email}'
        if current_user_type != UserTypes.new:
            # new users can't be cached
            v = await self.redis.get(user_node_key)
            if v:
                # user em2 node is cached, use that
                return v, email

        domain = email.rsplit('@', 1)[1]
        sub_domain = f'{em2_subdomain}.{domain}'
        domain_em2_platform = await self.cname_query(sub_domain)

        if domain_em2_platform:
            # domain has an em2 platform
            user_type = UserTypes.remote_em2
            try:
                r = await self.get(f'https://{domain_em2_platform}/route/', params={'email': email}, model=RouteModel)
            except HttpError:
                # domain has an em2 platform, but request failed, try again later
                node = RETRY
            else:
                node = r.model.node
                # 31_104_000 is one year, got a valid em2 node, assume it'll last for a long time
                await self.redis.setex(user_node_key, 31_104_000, node)
        else:
            # looks like domain doesn't support em2, smtp
            node = SMTP
            user_type = UserTypes.remote_other

        if current_user_type != user_type:
            await self.pg.execute('update users set user_type=$1, v=null where email=$2', user_type, email)
        return node, email

    async def cname_query(self, domain: str) -> str:
        domain_key = f'dns-cname:{domain}'
        ans = await self.redis.get(domain_key)
        null = '-'
        if ans:
            return None if ans == null else ans

        try:
            with timeout(5):
                v = await self.resolver.query(domain, 'CNAME')
        except (aiodns.error.DNSError, ValueError, asyncio.TimeoutError) as e:
            logger.debug('cname query error on %s, %s %s', domain, e.__class__.__name__, e)
            await self.redis.setex(domain_key, 3600, null)
        else:
            await self.redis.setex(domain_key, 3600, v.cname)
            return v.cname

    async def get(
        self,
        url,
        *,
        params: Dict[str, Any] = None,
        data: Any = None,
        headers: Dict[str, str] = None,
        model: Type[BaseModel] = None,
        expected_statuses: Sequence[int] = (200,),
    ):
        return await self._request('GET', url, params, data, headers, model, expected_statuses)

    async def post(
        self,
        url,
        *,
        params: Dict[str, Any] = None,
        data: Any = None,
        headers: Dict[str, str] = None,
        model: Type[BaseModel] = None,
        expected_statuses: Sequence[int] = (200,),
    ):
        return await self._request('POST', url, params, data, headers, model, expected_statuses)

    async def _request(self, method, url, params, data, headers, model, expected_statuses) -> ResponseSummary:

        response_headers = response_data = None
        if data:
            data_ = json.dumps(data)
        else:
            data_ = None

        if params:
            url = url + '?' + urlencode(params)

        try:
            async with self.session.request(method, url, data=data_, headers=headers) as r:
                response_data = await r.text()
                response_headers = dict(r.headers)

                if r.status in expected_statuses:
                    d = await r.json()
                    m = model.parse_obj(d) if model else None
                    return ResponseSummary(r.status, response_headers, d, m)

        except (ClientError, ClientConnectionError, asyncio.TimeoutError, ValueError) as e:
            exc = f'{e.__class__.__name__}: {e}'
        else:
            exc = f'bad response: {r.status}'

        logger.warning(
            'error on %s to %s, %s',
            method,
            url,
            exc,
            extra={
                'data': {
                    'method': method,
                    'url': url,
                    'request_data': data,
                    'request_headers': headers,
                    'response_headers': response_headers,
                    'response_data': lenient_json(response_data),
                }
            },
        )
        raise HttpError(f'error on {method} to {url}, {exc}')

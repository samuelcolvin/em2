import asyncio
import binascii
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Type

import aiodns
import nacl.encoding
from aiohttp import ClientError, ClientSession
from arq import ArqRedis
from async_timeout import timeout
from atoolbox import RequestError
from atoolbox.json_tools import lenient_json
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey
from pydantic import BaseModel, PositiveInt, UrlStr, ValidationError, constr
from yarl import URL

from em2.settings import Settings
from em2.utils.web import full_url, internal_request_headers

logger = logging.getLogger('em2.core')
# could try another subdomain with a random part incase people are using em2-platform
em2_subdomain = 'em2-platform'


class HttpError(RuntimeError):
    pass


class InvalidSignature(RuntimeError):
    pass


def get_signing_key(signing_secret_key) -> SigningKey:
    return SigningKey(seed=signing_secret_key, encoder=nacl.encoding.HexEncoder)


@dataclass
class ResponseSummary:
    status: int
    headers: Dict[str, str]
    model: Optional[BaseModel]


class RouteModel(BaseModel):
    node: UrlStr


class VerificationKeysModel(BaseModel):
    class KeyModel(BaseModel):
        key: constr(min_length=64, max_length=64)
        ttl: PositiveInt

    keys: List[KeyModel]


class Em2Comms:
    __slots__ = 'settings', 'session', 'signing_key', 'redis', 'resolver'

    def __init__(
        self,
        settings: Settings,
        session: ClientSession,
        signing_key: SigningKey,
        redis: ArqRedis,
        resolver: aiodns.DNSResolver,
    ):
        self.settings = settings
        self.session = session
        self.signing_key = signing_key
        self.redis = redis
        self.resolver = resolver

    def this_em2_node(self):
        # TODO different for test? include proto?
        return f'em2.{self.settings.domain}'

    async def check_signature(self, platform, request) -> None:  # noqa: C901 (ignore complexity)
        try:
            sig = request.headers['Signature']
        except KeyError:
            raise InvalidSignature('"Signature" header not found')

        try:
            ts_str, signature = sig.split(',', 1)
            ts = datetime.strptime(ts_str, '%Y-%m-%dT%H:%M:%S.%f')
            if len(signature) != 128:
                raise ValueError
            signature = bytes.fromhex(signature)
        except ValueError:
            raise InvalidSignature('Invalid "Signature" header format')

        now = datetime.utcnow()
        if not now - timedelta(seconds=30) < ts < now + timedelta(seconds=5):
            raise InvalidSignature('Signature expired')

        data = await request.read()
        body = body_to_sign(request.method, request.url, ts_str, data)

        signing_verify_cache_key = f'node-signing-verify:{platform}'
        signing_verify_key = await self.redis.get(signing_verify_cache_key)
        error = None
        if signing_verify_key:
            error = check_signature(signing_verify_key, signature, body)
            if not error:
                return

        url = platform + '/v1/signing/verification/'
        try:
            r = await self.get(url, sign=False, model=VerificationKeysModel)
        except HttpError:
            raise InvalidSignature(f'error getting signature from {url!r}')

        for m in r.model.keys:
            error = check_signature(m.key, signature, body)
            if not error:
                await self.redis.setex(signing_verify_cache_key, m.ttl, m.key)
                return

        raise InvalidSignature(error or 'No signature verification keys found')

    async def get_em2_node(self, email) -> Optional[str]:
        user_node_key = f'user-node:{email}'
        v = await self.redis.get(user_node_key)
        if v:
            # user em2 node is cached, use that
            return v

        domain = email.rsplit('@', 1)[1]
        sub_domain = f'{em2_subdomain}.{domain}'
        em2_domain = await self.cname_query(sub_domain)

        if not em2_domain:
            return

        scheme = 'http' if self.settings.testing else 'https'
        r = await self.get(f'{scheme}://{em2_domain}/v1/route/', sign=False, params={'email': email}, model=RouteModel)

        node = r.model.node.rstrip('/')
        # 31_104_000 is one year, got a valid em2 node, assume it'll last for a long time
        await self.redis.setex(user_node_key, 31_104_000, node)
        return node

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

    async def check_local(self, email):
        h = internal_request_headers(self.settings)
        url = full_url(self.settings, 'auth', '/check/')
        async with self.session.get(url, data=email, headers=h) as r:
            content = await r.read()

        if r.status != 200:
            raise RequestError(r.status, url, text=content.decode())

        return content == b'1'

    async def get(
        self,
        url: str,
        *,
        sign: bool = True,
        params: Dict[str, Any] = None,
        data: Any = None,
        model: Type[BaseModel] = None,
        expected_statuses: Sequence[int] = (200,),
    ):
        return await self._em2_request('GET', url, sign, params, data, model, expected_statuses)

    async def post(
        self,
        url: str,
        *,
        sign: bool = True,
        data: Any = None,
        params: Dict[str, Any] = None,
        model: Type[BaseModel] = None,
        expected_statuses: Sequence[int] = (200,),
    ):
        return await self._em2_request('POST', url, sign, params, data, model, expected_statuses)

    async def _em2_request(
        self,
        method: str,
        url: str,
        sign: bool,
        params: Optional[Dict[str, Any]],
        data: Any,
        model: Type[BaseModel],
        expected_statuses: Sequence[int],
    ) -> ResponseSummary:
        response_headers = response_data = None
        if isinstance(data, bytes):
            data_ = data
        elif data:
            data_ = json.dumps(data).encode()
        else:
            data_ = None

        url_ = URL(url)
        if params:
            url_ = url_.with_query(params)

        if sign:
            ts = datetime.utcnow().isoformat()
            to_sign = body_to_sign(method, url_, ts, data_)
            headers = {'Signature': ts + ',' + self.signing_key.sign(to_sign).signature.hex()}
        else:
            headers = None

        try:
            async with self.session.request(method, url_, data=data_, headers=headers) as r:
                response_data = await r.text()
                response_headers = dict(r.headers)

                if r.status in expected_statuses:
                    d, m = None, None
                    if model:
                        d = await r.json()
                        m = model.parse_obj(d)
                    return ResponseSummary(r.status, response_headers, m)

        except (ClientError, OSError, asyncio.TimeoutError, ValidationError) as e:
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


def body_to_sign(method: str, url: URL, ts: str, data: Optional[bytes]) -> bytes:
    return f'{method} {url} {ts}\n'.encode() + (data or b'-')


def check_signature(signing_verify_key: str, signature: bytes, body: bytes) -> str:
    try:
        verify_key = nacl.signing.VerifyKey(signing_verify_key, encoder=nacl.encoding.HexEncoder)
    except binascii.Error:
        return 'Invalid signature verification key'
    try:
        verify_key.verify(body, signature)
    except BadSignatureError:
        return 'Invalid signature'
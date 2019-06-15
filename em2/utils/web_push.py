import asyncio
import base64
import json
import time
from typing import Any, Optional
from urllib.parse import urlparse

import http_ece
from aiohttp import ClientSession
from atoolbox import RequestError
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02 as Vapid
from pydantic import BaseModel, UrlStr

from em2.settings import Settings
from em2.utils.db import Connections


def web_push_user_key(user_id):
    return f'web-push-subs:{user_id}'


class SubKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionModel(BaseModel):
    """
    Model as generated from PushSubscription.toJSON()
    https://developer.mozilla.org/en-US/docs/Web/API/PushSubscription/toJSON

    This is not a strict check of the structure since if people want to mess it up, we can't stop them
    """

    endpoint: UrlStr
    expirationTime: Optional[int]
    keys: SubKeys


async def subscribe(conns: Connections, m: SubscriptionModel, user_id):
    key = web_push_user_key(user_id)
    with await conns.redis as conn:
        await conn.unwatch()
        tr = conn.multi_exec()
        # might need a better unique and consistent way of referencing a subscription, then a hash
        # but try this first
        tr.sadd(key, m.json())
        # we could use expirationTime here, but it seems to generally be null
        tr.expire(key, 86400)
        await tr.execute()


async def unsubscribe(conns: Connections, m: SubscriptionModel, user_id):
    key = web_push_user_key(user_id)
    await conns.redis.srem(key, m.json())


async def web_push(ctx, user_id: int, data: Any):
    conns: Connections = ctx['conns']
    if not conns.settings.vapid_private_key or not conns.settings.vapid_sub_email:
        return
    session: ClientSession = ctx['session']
    subs = await conns.redis.smembers(web_push_user_key(user_id))
    if subs:
        await asyncio.gather(*[_sub_post(conns, session, s, user_id, data) for s in subs])
    return len(subs)


async def _sub_post(conns: Connections, session: ClientSession, sub_str: str, user_id: int, data: Any):
    sub = SubscriptionModel.parse_raw(sub_str, proto='json')
    server_key = ec.generate_private_key(ec.SECP256R1, default_backend())
    body = http_ece.encrypt(
        json.dumps(data).encode(),
        private_key=server_key,
        dh=_prepare_vapid_key(sub.keys.p256dh),
        auth_secret=_prepare_vapid_key(sub.keys.auth),
        version=vapid_encoding,
    )
    headers = _vapid_headers(sub, conns.settings)
    async with session.post(sub.endpoint, data=body, headers=headers) as r:
        text = await r.text()
    if r.status == 201:
        return
    elif r.status == 410:
        await unsubscribe(conns, sub, user_id)
    else:
        RequestError(r.status, sub.endpoint, text=text)


vapid_encoding = 'aes128gcm'


def _vapid_headers(sub: SubscriptionModel, settings: Settings):
    url = urlparse(sub.endpoint)
    vapid_claims = {
        'aud': f'{url.scheme}://{url.netloc}',
        'sub': 'mailto:' + settings.vapid_sub_email,
        'ext': int(time.time()) + 12 * 3600,
    }
    return {
        'ttl': '60',
        'content-encoding': vapid_encoding,
        **Vapid.from_string(private_key=settings.vapid_private_key).sign(vapid_claims),
    }


def _prepare_vapid_key(data: str) -> bytes:
    """
    Add base64 padding to the end of a string, if required
    """
    data = data.encode() + b'===='[: len(data) % 4]
    return base64.urlsafe_b64decode(data)

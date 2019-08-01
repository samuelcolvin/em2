import asyncio
import base64
import hashlib
import logging
import re
import time
from typing import Optional

import http_ece
import ujson
from aiohttp import ClientSession
from atoolbox import RequestError
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.asymmetric import ec
from py_vapid import Vapid02 as Vapid
from pydantic import BaseModel, UrlStr

from em2.core import get_flag_counts
from em2.settings import Settings
from em2.utils.db import Connections

logger = logging.getLogger('em2.web_push')


def web_push_user_key_prefix(user_id):
    return f'web-push-subs:{user_id}:'


class SubscriptionModel(BaseModel):
    """
    Model as generated from PushSubscription.toJSON()
    https://developer.mozilla.org/en-US/docs/Web/API/PushSubscription/toJSON
    """

    endpoint: UrlStr
    expirationTime: Optional[int]

    class SubKeys(BaseModel):
        p256dh: bytes
        auth: bytes

    keys: SubKeys

    def hash(self):
        return hashlib.md5(b'|'.join([self.endpoint.encode(), self.keys.p256dh, self.keys.auth])).hexdigest()


async def subscribe(conns: Connections, client_session: ClientSession, sub: SubscriptionModel, user_id):
    key = web_push_user_key_prefix(user_id) + sub.hash()
    # we could use expirationTime here, but it seems to generally be null
    await conns.redis.setex(key, 86400, sub.json())
    msg = await conns.main.fetchval(
        """
        select json_build_object('user_v', v, 'user_id', id)
        from users where id=$1
        """,
        user_id,
    )
    await _sub_post(conns, client_session, sub, user_id, msg)


async def unsubscribe(conns: Connections, sub: SubscriptionModel, user_id):
    key = web_push_user_key_prefix(user_id) + sub.hash()
    await conns.redis.delete(key)


async def web_push(ctx, actions_data: str):
    conns: Connections = ctx['conns']
    if not conns.settings.vapid_private_key or not conns.settings.vapid_sub_email:
        return 'web push not configured'

    session: ClientSession = ctx['client_session']
    data = ujson.loads(actions_data)
    participants = data.pop('participants')
    # hack to avoid building json for every user, remove the ending "}" so extra json can be appended
    msg_json_chunk = ujson.dumps(data)[:-1]
    coros = [_user_web_push(conns, session, p, msg_json_chunk) for p in participants]
    pushes = await asyncio.gather(*coros)
    return sum(pushes)


async def _user_web_push(conns: Connections, session: ClientSession, participant: dict, msg_json_chunk: str):
    user_id = participant['user_id']

    match = web_push_user_key_prefix(user_id) + '*'
    subs = []
    with await conns.redis as conn:
        cur = b'0'
        while cur:
            cur, keys = await conn.scan(cur, match=match)
            for key in keys:
                subs.append(await conn.get(key))

    if subs:
        participant['flags'] = await get_flag_counts(conns, user_id)
        msg = msg_json_chunk + ',' + ujson.dumps(participant)[1:]
        subs = [SubscriptionModel(**ujson.loads(s)) for s in subs]
        await asyncio.gather(*[_sub_post(conns, session, s, user_id, msg) for s in subs])
        return len(subs)
    else:
        return 0


async def _sub_post(conns: Connections, session: ClientSession, sub: SubscriptionModel, user_id: int, msg: str):
    body = http_ece.encrypt(
        msg.encode(),
        private_key=ec.generate_private_key(ec.SECP256R1, default_backend()),
        dh=_prepare_vapid_key(sub.keys.p256dh),
        auth_secret=_prepare_vapid_key(sub.keys.auth),
        version=vapid_encoding,
    )
    async with session.post(sub.endpoint, data=body, headers=_vapid_headers(sub, conns.settings)) as r:
        text = await r.text()
    if r.status == 410:
        await unsubscribe(conns, sub, user_id)
    elif r.status == 403 and text == 'invalid JWT provided\n':
        # seems to happen with https://fcm.googleapis.com/fcm/send/...
        await unsubscribe(conns, sub, user_id)
    elif r.status != 201:
        logger.error(
            f'unexpected response from webpush %s: %s',
            r.status,
            repr(text[:100]),
            extra={'headers': dict(r.headers), 'text': text, 'url': sub.endpoint},
        )
        raise RequestError(r.status, sub.endpoint, text=text)


vapid_encoding = 'aes128gcm'
aud_re = re.compile('https?://[^/]+')


def _vapid_headers(sub: SubscriptionModel, settings: Settings):
    vapid_claims = {
        'aud': aud_re.match(sub.endpoint).group(0),
        'sub': 'mailto:' + settings.vapid_sub_email,
        'ext': int(time.time()) + 300,
    }
    return {
        'ttl': '60',
        'content-encoding': vapid_encoding,
        **Vapid.from_string(private_key=settings.vapid_private_key).sign(vapid_claims),
    }


def _prepare_vapid_key(data: bytes) -> bytes:
    return base64.urlsafe_b64decode(data + b'===='[: len(data) % 4])

import base64
import hashlib
import hmac
import logging
import re
from binascii import hexlify
from datetime import datetime
from email.message import EmailMessage
from functools import reduce
from typing import Set
from urllib.parse import urlencode

from aiohttp import ClientSession, ClientTimeout
from atoolbox import RequestError

from .base_handler import BaseFallbackHandler

logger = logging.getLogger('em2.fallback.aws')

_AWS_HOST = 'email.{region}.amazonaws.com'
_AWS_ENDPOINT = 'https://{host}/'
_AWS_SERVICE = 'ses'
_AWS_AUTH_REQUEST = 'aws4_request'
_CONTENT_TYPE = 'application/x-www-form-urlencoded'
_SIGNED_HEADERS = 'content-type', 'host', 'x-amz-date'
_CANONICAL_REQUEST = """\
POST
/

{canonical_headers}
{signed_headers}
{payload_hash}"""
_AUTH_ALGORITHM = 'AWS4-HMAC-SHA256'
_CREDENTIAL_SCOPE = '{date_stamp}/{region}/{service}/{auth_request}'
_STRING_TO_SIGN = """\
{algorithm}
{x_amz_date}
{credential_scope}
{canonical_request_hash}"""
_AUTH_HEADER = (
    '{algorithm} Credential={access_key}/{credential_scope},SignedHeaders={signed_headers},Signature={signature}'
)


class SesFallbackHandler(BaseFallbackHandler):
    """
    Use AWS's SES service to send SMTP emails.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not (self.settings.ses_access_key and self.settings.ses_secret_key):
            raise RuntimeError(
                'both settings.ses_access_key and settings.ses_secret_key must be set to use SesFallbackHandler'
            )
        self.session = ClientSession(timeout=ClientTimeout(total=5))
        self._host = self.settings.ses_host.format(region=self.settings.ses_region)
        self._endpoint = self.settings.ses_endpoint.format(host=self._host)

    async def shutdown(self):
        await self.session.close()

    def _aws_headers(self, data):
        n = datetime.utcnow()
        x_amz_date = n.strftime('%Y%m%dT%H%M%SZ')
        date_stamp = n.strftime('%Y%m%d')
        ctx = dict(
            access_key=self.settings.ses_access_key,
            algorithm=_AUTH_ALGORITHM,
            x_amz_date=x_amz_date,
            auth_request=_AWS_AUTH_REQUEST,
            content_type=_CONTENT_TYPE,
            date_stamp=date_stamp,
            host=self._host,
            payload_hash=hashlib.sha256(data).hexdigest(),
            region=self.settings.ses_region,
            service=_AWS_SERVICE,
            signed_headers=';'.join(_SIGNED_HEADERS),
        )
        ctx.update(credential_scope=_CREDENTIAL_SCOPE.format(**ctx))
        canonical_headers = ''.join('{}:{}\n'.format(h, ctx[h.replace('-', '_')]) for h in _SIGNED_HEADERS)

        canonical_request = _CANONICAL_REQUEST.format(canonical_headers=canonical_headers, **ctx).encode()

        s2s = _STRING_TO_SIGN.format(canonical_request_hash=hashlib.sha256(canonical_request).hexdigest(), **ctx)

        key_parts = (
            b'AWS4' + self.settings.ses_secret_key.encode(),
            date_stamp,
            self.settings.ses_region,
            _AWS_SERVICE,
            _AWS_AUTH_REQUEST,
            s2s,
        )
        signature = reduce(lambda key, msg: hmac.new(key, msg.encode(), hashlib.sha256).digest(), key_parts)

        authorization_header = _AUTH_HEADER.format(signature=hexlify(signature).decode(), **ctx)
        return {'Content-Type': _CONTENT_TYPE, 'X-Amz-Date': x_amz_date, 'Authorization': authorization_header}

    async def send_message(self, *, e_from: str, to: Set[str], email_msg: EmailMessage):
        data = {
            'Action': 'SendRawEmail',
            'Source': e_from,
            'RawMessage.Data': base64.b64encode(email_msg.as_string().encode()),
        }
        data.update({f'Destination.ToAddresses.member.{i}': t.encode() for i, t in enumerate(to, start=1)})
        # data.update({f'Destination.BccAddresses.member.{i + 1}': t.encode() for i, t in enumerate(bcc)})
        data = urlencode(data).encode()

        headers = self._aws_headers(data)
        async with self.session.post(self._endpoint, data=data, headers=headers, timeout=5) as r:
            text = await r.text()
        if r.status != 200:
            raise RequestError(r.status, self._endpoint, text=text)
        msg_id = re.search('<MessageId>(.+?)</MessageId>', text).groups()[0]
        return msg_id + f'@{self.settings.ses_region}.amazonses.com'

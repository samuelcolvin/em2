import json

import nacl.encoding
import nacl.signing
from aiohttp import web
from atoolbox.middleware import pg_middleware

from em2.protocol.views.main import signing_verification
from em2.protocol.views.smtp_ses import ses_webhook
from em2.settings import Settings
from em2.utils.web import build_index


async def create_app_protocol(settings=None):
    app = web.Application(middlewares=[pg_middleware])

    settings = settings or Settings()
    signing_key = nacl.signing.SigningKey(seed=settings.signing_secret_key, encoder=nacl.encoding.HexEncoder)

    app.update(
        name='auth',
        settings=settings,
        signing_verification_response=json.dumps(
            {
                'version': settings.signing_version,
                'signing_verification_keys': [signing_key.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode()],
                'ttl': 86400,
            }
        ),
    )
    app.add_routes(
        [
            web.post('/webhook/ses/{token}/', ses_webhook, name='webhook-ses'),
            web.get('/signing/verification/', signing_verification, name='signing-verification'),
        ]
    )
    app['index_path'] = build_index(app, 'platform-to-platform interface')
    return app

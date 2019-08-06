import nacl.encoding
import nacl.signing
from aiodns import DNSResolver
from aiohttp import web
from atoolbox.middleware import pg_middleware

from em2.protocol.views.main import Em2Push, signing_verification
from em2.protocol.views.smtp_ses import ses_webhook
from em2.settings import Settings
from em2.utils.web import build_index

from .core import Em2Comms


async def startup(app):
    app['em2'] = Em2Comms(
        app['settings'],
        app['http_client'],
        app['signing_key'],
        app['redis'],
        DNSResolver(nameservers=['1.1.1.1', '1.0.0.1']),
    )


async def create_app_protocol(settings=None):
    app = web.Application(middlewares=[pg_middleware])

    settings = settings or Settings()
    app.update(
        name='auth',
        settings=settings,
        signing_key=nacl.signing.SigningKey(seed=settings.signing_secret_key, encoder=nacl.encoding.HexEncoder),
    )
    app.on_startup.append(startup)
    app.add_routes(
        [
            web.post('/webhook/ses/{token}/', ses_webhook, name='webhook-ses'),
            web.get('/v1/signing/verification/', signing_verification, name='signing-verification'),
            web.post('/v1/push/', Em2Push.view(), name='em2-push'),
        ]
    )
    app['index_path'] = build_index(app, 'platform-to-platform interface')
    return app

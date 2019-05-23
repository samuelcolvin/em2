from aiohttp import web
from atoolbox.middleware import pg_middleware

from em2.protocol.views.smtp_ses import ses_webhook
from em2.settings import Settings
from em2.utils.web import build_index


async def create_app_protocol(settings=None):
    routes = [web.post('/webhook/ses/{token}/', ses_webhook, name='webhook-ses')]
    middleware = [pg_middleware]
    app = web.Application(middlewares=middleware)
    app.update(name='auth', settings=settings or Settings())
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'platform-to-platform interface')
    return app

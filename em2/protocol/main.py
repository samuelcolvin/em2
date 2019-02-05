from aiohttp import web

from em2.protocol.views import testing_view
from em2.settings import Settings
from em2.utils.web import build_index


async def create_app_protocol(settings=None):
    routes = [web.get('/testing/', testing_view, name='testing')]
    app = web.Application()
    app.update(name='auth', settings=settings or Settings())
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'platform-to-platform interface')
    return app

from aiohttp import web

from atoolbox.middleware import csrf_middleware
from settings import Settings
from utils.auth import add_access_control
from utils.views import build_index


async def create_app_auth(settings=None):
    settings = settings or Settings()
    routes = [
    ]
    middleware = (csrf_middleware,)
    app = web.Application(middlewares=middleware)
    app['settings'] = settings or Settings()
    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'auth interface')
    return app

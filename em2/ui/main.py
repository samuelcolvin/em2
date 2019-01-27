from aiohttp import web
from aiohttp_session import session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from atoolbox.middleware import csrf_middleware
from settings import Settings
from utils.auth import add_access_control
from utils.views import build_index


async def create_app_ui(settings=None):
    settings = settings or Settings()
    routes = [
    ]
    middleware = (
        session_middleware(EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)),
        csrf_middleware,
    )
    app = web.Application(middlewares=middleware)
    app['settings'] = settings
    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'user interface')
    return app

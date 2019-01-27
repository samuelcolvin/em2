from aiohttp import web
from aiohttp_session import session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage

from atoolbox.middleware import csrf_middleware, pg_middleware
from cryptography import fernet

from settings import Settings
from utils.web import add_access_control, build_index

from .middleware import user_middleware
from .views.auth import AuthExchangeToken
from .views.main import VList


async def create_app_ui(settings=None):
    settings = settings or Settings()
    routes = [
        web.route('*', '/auth/', AuthExchangeToken.view(), name='auth'),
        web.get('/list/', VList.view(), name='list'),
    ]
    middleware = (
        session_middleware(EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)),
        user_middleware,
        csrf_middleware,
        pg_middleware,
    )
    app = web.Application(middlewares=middleware)
    app.update(
        settings=settings,
        auth_fernet=fernet.Fernet(settings.auth_key),
    )
    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'user interface')
    return app

from aiohttp import web
from atoolbox.middleware import pg_middleware
from cryptography import fernet

from settings import Settings
from utils.middleware import csrf_middleware
from utils.web import add_access_control, build_index

from .utils import mk_password
from .views.main import Login


async def create_app_auth(settings=None):
    settings = settings or Settings()
    routes = [web.route('*', '/login/', Login.view(), name='login')]
    middleware = (csrf_middleware, pg_middleware)
    app = web.Application(middlewares=middleware)
    app.update(
        name='auth',
        settings=settings,
        dummy_password_hash=mk_password(settings.dummy_password, settings),
        auth_fernet=fernet.Fernet(settings.auth_key),
    )
    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'auth interface')
    return app

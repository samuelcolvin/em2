from aiohttp import web
from atoolbox.middleware import pg_middleware
from cryptography import fernet

from em2.settings import Settings
from em2.utils.middleware import csrf_middleware
from em2.utils.web import add_access_control, build_index

from .utils import mk_password
from .views.main import Login, Logout, UpdateSession, check_address


async def create_app_auth(settings=None):
    settings = settings or Settings()
    routes = [
        web.route('*', '/login/', Login.view(), name='login'),
        web.post('/logout/', Logout.view(), name='logout'),
        web.post('/update-session/', UpdateSession.view(), name='update-session'),
        web.get('/check/', check_address, name='check-address'),
    ]
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

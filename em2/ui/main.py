from aiohttp import web
from aiohttp_session import session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from atoolbox.middleware import pg_middleware
from cryptography import fernet

from em2.settings import Settings
from em2.utils.middleware import csrf_middleware
from em2.utils.web import add_access_control, build_index

from .middleware import user_middleware
from .views.auth import AuthExchangeToken
from .views.contacts import ContactSearch
from .views.conversations import ConvActions, ConvCreate, ConvList


async def create_app_ui(settings=None):
    settings = settings or Settings()
    conv_match = r'{conv:[a-z0-9\-]{10,64}}'
    routes = [
        web.route('*', '/auth-token/', AuthExchangeToken.view(), name='auth-token'),
        web.get('/list/', ConvList.view(), name='list'),
        web.route('*', '/create/', ConvCreate.view(), name='create'),
        web.get(f'/conv/{conv_match}/', ConvActions.view(), name='get-conv'),
        web.get('/contacts/lookup-email/', ContactSearch.view(), name='contacts-lookup-email'),
    ]
    middleware = (
        csrf_middleware,
        session_middleware(EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)),
        user_middleware,
        pg_middleware,
    )
    app = web.Application(middlewares=middleware)
    app.update(name='ui', settings=settings, auth_fernet=fernet.Fernet(settings.auth_key))
    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'user interface')
    return app

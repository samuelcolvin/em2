from aiohttp import web
from aiohttp_session import session_middleware
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from atoolbox.middleware import pg_middleware
from cryptography import fernet

from em2.background import Background
from em2.settings import Settings
from em2.utils.middleware import csrf_middleware
from em2.utils.web import add_access_control, build_index

from .middleware import user_middleware
from .views import online
from .views.auth import AuthExchangeToken, logout
from .views.contacts import ContactSearch
from .views.conversations import ConvAct, ConvActions, ConvCreate, ConvList, ConvPublish
from .views.ws import websocket


async def startup(app):
    app.update(background=Background(app))


no_pg_conn = {'ui.index', 'ui.online', 'ui.websocket'}


def pg_middleware_check(request):
    return request['view_name'] not in no_pg_conn


async def create_app_ui(settings=None):
    settings = settings or Settings()
    conv_match = r'{conv:[a-f0-9]{10,64}}'
    routes = [
        web.get('/online/', online, name='online'),
        web.get('/conv/list/', ConvList.view(), name='list'),
        web.route('*', '/conv/create/', ConvCreate.view(), name='create'),
        web.get(f'/conv/{conv_match}/', ConvActions.view(), name='get'),
        web.post(f'/conv/{conv_match}/act/', ConvAct.view(), name='act'),
        web.post(f'/conv/{conv_match}/publish/', ConvPublish.view(), name='publish'),
        web.get('/ws/', websocket, name='websocket'),
        # ui auth views:
        web.route('*', '/auth/token/', AuthExchangeToken.view(), name='auth-token'),
        web.post('/auth/logout/', logout, name='auth-logout'),
        # different app?:
        web.get('/contacts/lookup-email/', ContactSearch.view(), name='contacts-lookup-email'),
    ]
    middleware = (
        csrf_middleware,
        session_middleware(EncryptedCookieStorage(settings.auth_key, cookie_name=settings.cookie_name)),
        user_middleware,
        pg_middleware,
    )
    app = web.Application(middlewares=middleware)
    app.update(
        name='ui',
        settings=settings,
        auth_fernet=fernet.Fernet(settings.auth_key),
        pg_middleware_check=pg_middleware_check,
    )

    app.on_startup.append(startup)

    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'user interface')
    return app

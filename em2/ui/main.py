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
from .views.conversations import (
    ConvAct,
    ConvActions,
    ConvCreate,
    ConvList,
    ConvPublish,
    GetConvCounts,
    GetFile,
    SetConvState,
)
from .views.labels import AddRemoveLabel, LabelBread
from .views.ws import websocket


async def startup(app):
    app.update(background=Background(app))


no_pg_conn = {'ui.index', 'ui.online', 'ui.websocket'}


def pg_middleware_check(request):
    return request['view_name'] not in no_pg_conn


async def create_app_ui(settings=None):
    settings = settings or Settings()
    conv_match = r'{conv:[a-f0-9]{10,64}}'
    s = r'/{session_id:\d+}/'
    routes = [
        web.get('/online/', online, name='online'),
        web.get(s + 'conv/list/', ConvList.view(), name='list'),
        web.route('*', s + 'conv/create/', ConvCreate.view(), name='create'),
        web.get(s + 'conv/counts/', GetConvCounts.view(), name='conv-counts'),
        web.get(s + f'conv/{conv_match}/', ConvActions.view(), name='get'),
        web.post(s + f'conv/{conv_match}/act/', ConvAct.view(), name='act'),
        web.post(s + f'conv/{conv_match}/publish/', ConvPublish.view(), name='publish'),
        web.post(s + f'conv/{conv_match}/set-state/', SetConvState.view(), name='set-conv-state'),
        web.post(s + f'conv/{conv_match}/set-label/', AddRemoveLabel.view(), name='add-remove-label'),
        *LabelBread.routes(s + 'labels/', name='labels'),
        # no trailing slash so we capture everything and deal with weird/ugly content ids
        web.get(s + fr'img/{conv_match}/{{content_id:.*}}', GetFile.view(), name='get-file'),
        web.get(s + 'ws/', websocket, name='websocket'),
        # ui auth views:
        web.route('*', '/auth/token/', AuthExchangeToken.view(), name='auth-token'),
        web.post(s + 'auth/logout/', logout, name='auth-logout'),
        # different app?:
        web.get(s + 'contacts/lookup-email/', ContactSearch.view(), name='contacts-lookup-email'),
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

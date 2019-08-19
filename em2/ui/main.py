from typing import Optional

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
from .views.auth import AuthExchangeToken, auth_check, logout
from .views.contacts import ContactSearch
from .views.conversations import (
    ConvAct,
    ConvActions,
    ConvCreate,
    ConvDetails,
    ConvList,
    ConvPublish,
    GetConvCounts,
    Search,
    SetConvFlag,
)
from .views.files import GetFile, GetHtmlImage, UploadFile
from .views.labels import AddRemoveLabel, LabelBread
from .views.realtime import WebPushSubscribe, WebPushUnsubscribe, websocket


async def startup(app):
    app.update(background=Background(app))


no_pg_conn = {'ui.index', 'ui.websocket'}


def pg_middleware_check(request):
    return request['view_name'] not in no_pg_conn


async def create_app_ui(main_app: Optional[web.Application]):
    settings: Settings = main_app['settings']
    conv_match = r'{conv:[a-f0-9]{10,64}}'
    s = r'/{session_id:\d+}/'
    routes = [
        web.get(s + 'conv/list/', ConvList.view(), name='list'),
        web.route('*', s + 'conv/create/', ConvCreate.view(), name='create'),
        web.get(s + 'conv/counts/', GetConvCounts.view(), name='conv-counts'),
        web.get(s + f'conv/{conv_match}/actions/', ConvActions.view(), name='get-actions'),
        web.get(s + f'conv/{conv_match}/details/', ConvDetails.view(), name='get-details'),
        web.post(s + f'conv/{conv_match}/act/', ConvAct.view(), name='act'),
        web.post(s + f'conv/{conv_match}/publish/', ConvPublish.view(), name='publish'),
        web.post(s + f'conv/{conv_match}/set-flag/', SetConvFlag.view(), name='set-conv-flag'),
        web.post(s + f'conv/{conv_match}/set-label/', AddRemoveLabel.view(), name='add-remove-label'),
        *LabelBread.routes(s + 'labels/', name='labels'),
        # no trailing slash so we capture everything and deal with weird/ugly content ids
        web.get(s + fr'conv/{conv_match}/file/{{content_id:.*}}', GetFile.view(), name='get-file'),
        web.get(s + fr'conv/{conv_match}/html-image/{{url:.*}}', GetHtmlImage.view(), name='get-html-image'),
        web.get(s + fr'conv/{conv_match}/upload-file/', UploadFile.view(), name='upload-file'),
        web.get(s + 'search/', Search.view(), name='search'),
        web.get(s + 'ws/', websocket, name='websocket'),
        web.post(s + 'webpush-subscribe/', WebPushSubscribe.view(), name='webpush-subscribe'),
        web.post(s + 'webpush-unsubscribe/', WebPushUnsubscribe.view(), name='webpush-unsubscribe'),
        # ui auth views:
        web.route('*', '/auth/token/', AuthExchangeToken.view(), name='auth-token'),
        web.get(s + 'auth/check/', auth_check, name='auth-check'),
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
        main_app=main_app,
        settings=settings,
        auth_fernet=fernet.Fernet(settings.auth_key),
        pg_middleware_check=pg_middleware_check,
    )

    app.on_startup.append(startup)

    add_access_control(app)
    app.add_routes(routes)
    app['index_path'] = build_index(app, 'user interface')
    return app

import logging
import sys
from datetime import datetime

from aiohttp.web import Application
from atoolbox.create_app import cleanup, startup
from atoolbox.middleware import error_middleware

from em2.auth import create_app_auth
from em2.protocol import create_app_protocol
from em2.settings import SRC_DIR, Settings
from em2.ui import create_app_ui
from em2.utils.web import build_index

logger = logging.getLogger('em2.main')
copied_context = 'pg', 'redis', 'http_client', 'expected_origin'


async def startup_populate_subapps(app: Application):
    subapp_context = {f: app[f] for f in copied_context}
    app['ui_app'].update(subapp_context)
    app['protocol_app'].update(subapp_context)
    app['auth_app'].update(subapp_context)


async def restart_react_dev_server(app: Application):
    """
    For development only. Prompts CRA's "yarn start" dev server to reload.
    """
    settings: Settings = app['settings']
    if settings.domain == 'localhost' and 'runserver' in sys.argv:  # basic proxy for "development mode"
        path = SRC_DIR / '../js/src/.update.js'
        if path.parent.exists():
            path.write_text(f'// {datetime.now():%H:%M:%S}')
        else:
            logger.warning('update.js directory "%s" does not exist', path.resolve())


def should_warn(r):
    return r.status > 310


async def create_app(settings: Settings = None):
    settings = settings or Settings()
    middleware = () if settings.domain == 'localhost' else (error_middleware,)
    app = Application(middlewares=middleware, client_max_size=settings.max_request_size)

    app['settings'] = settings
    app.update(
        middleware_should_warn=should_warn,
        ui_app=await create_app_ui(app),
        protocol_app=await create_app_protocol(app),
        auth_app=await create_app_auth(app),
    )
    app.on_startup.append(startup)
    app.on_startup.append(startup_populate_subapps)
    app.on_startup.append(restart_react_dev_server)
    app.on_cleanup.append(cleanup)

    if settings.domain == 'localhost':
        # development mode, route apps via path
        app.add_subapp('/ui/', app['ui_app'])
        app.add_subapp('/em2/', app['protocol_app'])
        app.add_subapp('/auth/', app['auth_app'])
        routes_description = (
            f'  http://localhost:{settings.local_port}/ui/ - user interface routes\n'
            f'  http://localhost:{settings.local_port}/em2/ - em2 protocol routes\n'
            f'  http://localhost:{settings.local_port}/auth/ - auth routes\n'
        )
        app['expected_origin'] = 'http://localhost:3000'
    else:
        app.add_domain('ui.' + settings.domain, app['ui_app'])
        app.add_domain('em2.' + settings.domain, app['protocol_app'])
        app.add_domain('auth.' + settings.domain, app['auth_app'])
        app['expected_origin'] = f'https://app.{settings.domain}'
        routes_description = (
            f'  https://ui.{settings.domain}/ - user interface routes\n'
            f'  https://em2.{settings.domain}/ - em2 protocol routes\n'
            f'  https://auth.{settings.domain}/ - auth routes\n'
        )
    app['index_path'] = build_index(app, 'root interface', routes_description)
    return app

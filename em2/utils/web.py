import json
import secrets
from time import time
from typing import Tuple

from aiohttp import web
from aiohttp.abc import Application
from aiohttp.web_exceptions import HTTPForbidden
from aiohttp.web_fileresponse import FileResponse
from atoolbox.utils import get_ip, slugify

from em2.settings import SRC_DIR, Settings

index_text = """\
em2 {name}
commit: {commit}
build time: {build_time}

{routes}
"""


def build_index(app: web.Application, name: str, routes: str = None):
    app.add_routes([index_route])
    routes = routes or '\n'.join(f'  {r.canonical} - {r.name}' for r in app.router.values())
    text = index_text.format(
        commit=app['settings'].commit, build_time=app['settings'].build_time, name=name, routes=routes
    )
    p = SRC_DIR / '.index' / f'index.{slugify(name)}.txt'
    p.parent.mkdir(exist_ok=True)
    p.write_text(text)
    return p


async def index_view(request):
    # TODO this might be much slower than just returning the raw string
    return FileResponse(request.app['index_path'])


index_route = web.get('/', index_view, name='index')


def add_access_control(app: web.Application):
    settings: Settings = app['settings']

    async def _run(request, response):
        if 'Access-Control-Allow-Origin' not in response.headers:
            if settings.any_origin:
                # from chrome: The value of the 'Access-Control-Allow-Origin' header in the response must not be
                # the wildcard '*' when the request's credentials mode is 'include'.
                origin = request.headers.get('Origin', '*')
            else:
                origin = app['expected_origin']
            response.headers.update({'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true'})

    app.on_response_prepare.append(_run)


class MakeUrl:
    __slots__ = ('main_app',)

    def __init__(self, main_app: Application):
        self.main_app = main_app

    def __call__(self, name, *, query=None, **kwargs):
        # TODO if this is used in main code base it should be moved there and reused.
        try:
            app_name, route_name = name.split(':')
        except ValueError:
            raise RuntimeError('not app name, use format "<app name>:<route name>"')

        try:
            app = self.main_app[app_name + '_app']
        except KeyError:
            raise RuntimeError('app not found, options are : "ui", "protocol" and "auth"')

        try:
            r = app.router[route_name]
        except KeyError as e:
            route_names = ', '.join(sorted(app.router._named_resources))
            raise RuntimeError(f'route "{route_name}" not found, options are: {route_names}') from e

        assert None not in kwargs.values(), f'invalid kwargs, includes None: {kwargs}'
        url = r.url_for(**{k: str(v) for k, v in kwargs.items()})
        if query:
            url = url.with_query(**query)
        return url


def full_url(settings: Settings, app: str, path: str):
    if app == 'protocol':
        app = 'em2'

    assert app in {'em2', 'auth', 'ui'}, f'unknown app {app!r}, should be "em2", "auth", or "ui"'
    assert path.startswith('/'), f'part should start with /, not {path!r}'

    if settings.domain == 'localhost':
        root = f'http://localhost:{settings.local_port}/{app}'
    else:
        root = f'https://{app}.{settings.domain}'

    return root + path


def session_event(request, action_type) -> Tuple[str, int]:
    ts = int(time())
    event = json.dumps(
        {
            'ip': get_ip(request),
            'ts': ts,
            'ua': request.headers.get('User-Agent'),
            'ac': action_type,
            # TODO include info about which session this is when multiple sessions are active
        }
    )
    return event, ts


def internal_request_check(request):
    auth_header = request.headers.get('Authentication', '-')
    if not secrets.compare_digest(auth_header, request.app['settings'].internal_auth_key):
        raise HTTPForbidden(text='invalid Authentication header')


def internal_request_headers(settings):
    return {'Authentication': settings.internal_auth_key}

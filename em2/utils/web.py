from aiohttp import web
from aiohttp.abc import Application
from aiohttp.web_fileresponse import FileResponse
from atoolbox.utils import slugify

from em2.settings import SRC_DIR

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
    async def _run(request, response):
        if 'Access-Control-Allow-Origin' not in response.headers:
            response.headers.update(
                {
                    'Access-Control-Allow-Origin': request.app['expected_origin'],
                    'Access-Control-Allow-Credentials': 'true',
                }
            )

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

from aiohttp import web
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

from pathlib import Path

from aiohttp import web
from aiohttp.hdrs import METH_POST
from aiohttp.web_fileresponse import FileResponse
from aiohttp.web_response import Response
from atoolbox.class_views import ExecView as _ExecView
from atoolbox.middleware import CROSS_ORIGIN_ANY
from atoolbox.utils import slugify, JsonErrors

from settings import Settings

ROOT_DIR = Path(__file__).parent.parent


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
        commit=app['settings'].commit,
        build_time=app['settings'].build_time,
        name=name,
        routes=routes
    )
    p = ROOT_DIR / f'index.{slugify(name)}.txt'
    p.write_text(text)
    return p


async def index_view(request):
    return FileResponse(request.app['index_path'])


index_route = web.get('/', index_view, name='index')


def add_access_control(app: web.Application):

    async def _run(request, response):
        if 'Access-Control-Allow-Origin' not in response.headers:
            response.headers.update({
                'Access-Control-Allow-Origin': request.app['expected_origin'],
                'Access-Control-Allow-Credentials': 'true',
            })
    app.on_response_prepare.append(_run)


class ExecView(_ExecView):
    null_origin = False

    def build_headers(self):
        headers = super().build_headers()
        if not headers and self.null_origin:
            headers = {'Access-Control-Allow-Origin': 'null'}
        return headers

    async def options(self):
        acrm = self.request.headers.get('Access-Control-Request-Method')
        if acrm != METH_POST or self.request.headers.get('Access-Control-Request-Headers').lower() != 'content-type':
            raise JsonErrors.HTTPForbidden('Access-Control checks failed', headers=CROSS_ORIGIN_ANY)

        origin = 'null' if self.null_origin else self.request.app['expected_origin']

        if self.request.headers['origin'] != origin:
            raise JsonErrors.HTTPForbidden('Access-Control checks failed, wrong origin', headers=CROSS_ORIGIN_ANY)

        headers = {
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Origin': origin,
            'Access-Control-Allow-Credentials': 'true',
        }
        return Response(text='ok', headers=headers)

from pathlib import Path

from aiohttp import web
from aiohttp.web_fileresponse import FileResponse
from atoolbox.class_views import ExecView as _ExecView, View as _View
from atoolbox.utils import JsonErrors, slugify

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


async def _fetch404(func, sql, *args, msg_=None, **kwargs):
    """
    fetch from the db, raise not found if the value is doesn't exist
    """
    val = await func(sql, *args, **kwargs)
    if not val:
        raise JsonErrors.HTTPNotFound(msg_ or 'unable to find value in db')
    return val


class Fetch404Mixin:
    conn = NotImplemented

    async def fetchval404(self, sql, *args, msg_=None):
        return await _fetch404(self.conn.fetchval, sql, *args, msg_=msg_)

    async def fetchrow404(self, sql, *args, msg_=None):
        return await _fetch404(self.conn.fetchrow, sql, *args, msg_=msg_)

    async def fetchval404_b(self, sql, *args, msg_=None, **kwargs):
        return await _fetch404(self.conn.fetchval_b, sql, *args, **kwargs, msg_=msg_)

    async def fetchrow404_b(self, sql, *args, msg_=None, **kwargs):
        return await _fetch404(self.conn.fetchrow_b, sql, *args, **kwargs, msg_=msg_)


class View(Fetch404Mixin, _View):
    pass


class ExecView(Fetch404Mixin, _ExecView):
    pass

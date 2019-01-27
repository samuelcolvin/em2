from pathlib import Path

from aiohttp import web
from aiohttp.web_fileresponse import FileResponse
from atoolbox.utils import slugify

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

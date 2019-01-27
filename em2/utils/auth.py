from aiohttp.web_app import Application

from settings import Settings


def add_access_control(app: Application):
    settings: Settings = app['settings']
    if settings.domain != 'localhost':
        origin = f'https://app.{settings.domain}'

        async def _run(request, response):
            response.headers.update({
                'Access-Control-Allow-Origin': origin,
                'Access-Control-Allow-Credentials': 'true',
            })
        app.on_response_prepare.append(_run)

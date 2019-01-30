from aiohttp.hdrs import METH_OPTIONS, METH_GET
from aiohttp.web_middlewares import middleware
from aiohttp.web_urldispatcher import MatchInfoError
from atoolbox import JsonErrors
from atoolbox.middleware import CROSS_ORIGIN_ANY
from atoolbox.utils import JSON_CONTENT_TYPE
from yarl import URL


CSRF_IGNORE_VIEWS = set()
CSRF_UPLOAD_VIEW = set()
NULL_ORIGIN_VIEWS = {'auth.login'}


def csrf_checks(request):
    """
    Content-Type, Origin and Referrer checks for CSRF.
    """
    if request.method in {METH_OPTIONS, METH_GET} or isinstance(request.match_info, MatchInfoError):
        return

    view_name = request.app['name'] + '.' + request.match_info.route.name

    if view_name in CSRF_IGNORE_VIEWS:
        return

    ct = request.headers.get('Content-Type', '')
    if view_name in CSRF_UPLOAD_VIEW:
        if not ct.startswith('multipart/form-data; boundary'):
            return 'upload path, wrong Content-Type'
    elif not ct == JSON_CONTENT_TYPE:
        return 'Content-Type not application/json'

    origin = request.headers.get('Origin')
    if not origin:
        # being strict here and requiring Origin to be present, are there any cases where this breaks?
        return 'Origin missing'

    if view_name in NULL_ORIGIN_VIEWS:
        expected_origin = 'null'
        expected_referrer = None  # iframes without same-origin send no referrer
    else:
        expected_origin = request.app['expected_origin']
        expected_referrer = expected_origin

    if origin != expected_origin:
        return f'Origin wrong {origin!r} != {expected_origin!r}'

    referrer = request.headers.get('Referer')
    referrer_root = referrer and str(URL(referrer).origin())

    if referrer_root != expected_referrer:
        return f'Referer root wrong {referrer_root!r} != {expected_referrer!r}'


@middleware
async def csrf_middleware(request, handler):
    csrf_error = csrf_checks(request)
    if csrf_error:
        raise JsonErrors.HTTPForbidden('CSRF failure: ' + csrf_error, headers=CROSS_ORIGIN_ANY)
    else:
        return await handler(request)

from aiohttp.hdrs import METH_OPTIONS, METH_POST, METH_GET
from aiohttp.web_middlewares import middleware
from aiohttp.web_response import Response
from aiohttp.web_urldispatcher import MatchInfoError
from atoolbox import JsonErrors
from atoolbox.middleware import CROSS_ORIGIN_ANY
from atoolbox.utils import JSON_CONTENT_TYPE
from yarl import URL

from settings import Settings


def _get_view_name(request):
    return request.app['name'] + '.' + request.match_info.route.name


CSRF_IGNORE_VIEWS = set()
CSRF_UPLOAD_VIEW = set()
NULL_ORIGIN_VIEWS = {'auth.login'}


def csrf_checks(request, settings: Settings):
    """
    Content-Type, Origin and Referrer checks for CSRF.
    """
    view_name = _get_view_name(request)

    if view_name in CSRF_IGNORE_VIEWS:
        return

    ct = request.headers.get('Content-Type', '')
    if view_name in CSRF_UPLOAD_VIEW:
        if not ct.startswith('multipart/form-data; boundary'):
            return 'upload path, wrong Content-Type'
    else:
        if not ct == JSON_CONTENT_TYPE:
            return 'Content-Type not application/json'

    origin = request.headers.get('Origin')
    if not origin:
        # being strict here and requiring Origin to be present, are there any cases where this breaks
        return 'Origin missing'

    if view_name in NULL_ORIGIN_VIEWS:
        expected_origin = 'null'
        expected_referrer = None
    else:
        expected_origin = request.app['expected_origin']
        expected_referrer = expected_origin

    if origin != expected_origin:
        return f'Origin wrong {origin!r} != {expected_origin!r}'

    referrer = request.headers.get('Referer')
    if referrer:
        referrer_url = URL(referrer)
        referrer_root = referrer_url.scheme + '://' + referrer_url.host
    else:
        referrer_root = None

    if referrer_root != expected_referrer:
        return f'Referer root wrong {referrer_root!r} != {expected_referrer!r}'


def preflight_checks(request):
    if (
        request.headers.get('Access-Control-Request-Method') != METH_POST
        or request.headers.get('Access-Control-Request-Headers').lower() != 'content-type'
    ):
        raise JsonErrors.HTTPForbidden('Access-Control checks failed', headers=CROSS_ORIGIN_ANY)

    if _get_view_name(request) in NULL_ORIGIN_VIEWS:
        origin = 'null'
    else:
        origin = request.app['expected_origin']

    if request.headers['origin'] != origin:
        raise JsonErrors.HTTPForbidden('Access-Control checks failed, wrong origin', headers=CROSS_ORIGIN_ANY)

    headers = {'Access-Control-Allow-Headers': 'Content-Type', 'Access-Control-Allow-Origin': origin}
    return Response(text='ok', headers=headers)


@middleware
async def csrf_middleware(request, handler):
    if isinstance(request.match_info, MatchInfoError):
        return await handler(request)

    if request.method == METH_OPTIONS and 'Access-Control-Request-Method' in request.headers:
        return preflight_checks(request)
    elif request.method != METH_GET:
        csrf_error = csrf_checks(request, request.app['settings'])
        if csrf_error:
            raise JsonErrors.HTTPForbidden('CSRF failure: ' + csrf_error, headers=CROSS_ORIGIN_ANY)

    return await handler(request)

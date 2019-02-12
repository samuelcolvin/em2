from aiohttp.hdrs import METH_GET, METH_HEAD, METH_OPTIONS, METH_POST
from aiohttp.web_middlewares import middleware
from aiohttp.web_response import Response
from aiohttp.web_urldispatcher import MatchInfoError
from atoolbox import JsonErrors
from atoolbox.middleware import CROSS_ORIGIN_ANY
from atoolbox.utils import JSON_CONTENT_TYPE
from yarl import URL

CSRF_IGNORE_VIEWS = set()
CSRF_UPLOAD_VIEW = set()
NULL_ORIGIN_VIEWS = {'auth.login'}


def _view_name(request):
    if not isinstance(request.match_info, MatchInfoError):
        return request.app['name'] + '.' + request.match_info.route.name


def csrf_checks(request):
    """
    Content-Type, Origin and Referrer checks for CSRF.
    """
    view_name = request['view_name']
    if view_name is None or view_name in CSRF_IGNORE_VIEWS:
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


def preflight_check(request, acrm):
    if acrm != METH_POST or request.headers.get('Access-Control-Request-Headers').lower() != 'content-type':
        raise JsonErrors.HTTPForbidden('Access-Control checks failed', headers=CROSS_ORIGIN_ANY)

    origin = 'null' if request['view_name'] in NULL_ORIGIN_VIEWS else request.app['expected_origin']

    if request.headers['origin'] != origin:
        raise JsonErrors.HTTPForbidden('Access-Control checks failed, wrong origin', headers=CROSS_ORIGIN_ANY)

    headers = {
        'Access-Control-Allow-Headers': 'Content-Type',
        'Access-Control-Allow-Origin': origin,
        'Access-Control-Allow-Credentials': 'true',
    }
    return Response(text='ok', headers=headers)


@middleware
async def csrf_middleware(request, handler):
    request['view_name'] = _view_name(request)
    if request.method == METH_OPTIONS:
        acrm = request.headers.get('Access-Control-Request-Method')
        if acrm:
            return preflight_check(request, acrm)
    elif request.method not in {METH_GET, METH_HEAD}:
        csrf_error = csrf_checks(request)
        if csrf_error:
            raise JsonErrors.HTTPForbidden('CSRF failure: ' + csrf_error, headers=CROSS_ORIGIN_ANY)

    return await handler(request)

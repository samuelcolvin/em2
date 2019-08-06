import json

from aiohttp.web_exceptions import HTTPVersionNotSupported
from atoolbox import JsonErrors, raw_json_response
from atoolbox.utils import JSON_CONTENT_TYPE


async def signing_verification(request):
    try:
        version = int(request.query['version'])
    except KeyError:
        raise JsonErrors.HTTPBadRequest('version parameter missing')
    except ValueError:
        raise JsonErrors.HTTPBadRequest('invalid version parameter')

    supported_version = request.app['settings'].signing_version
    if version != supported_version:
        raise HTTPVersionNotSupported(
            text=json.dumps({'message': 'unsupported version', 'supported_versions': [supported_version]}),
            content_type=JSON_CONTENT_TYPE,
        )
    return raw_json_response(request.app['signing_verification_response'])

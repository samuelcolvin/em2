import logging
from typing import cast

from arq import ArqRedis
from atoolbox import JsonErrors
from atoolbox.class_views import ExecView as _ExecView

from em2.protocol.core import Em2Comms, InvalidSignature
from em2.utils.db import conns_from_request

logger = logging.getLogger('em2.protocol.views')


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.redis = cast(ArqRedis, self.redis)
        self.conns = conns_from_request(self.request)
        self.em2: Em2Comms = self.app['em2']


async def check_signature(request):
    try:
        request_em2_node = request.query['node']
    except KeyError:
        raise JsonErrors.HTTPBadRequest("'node' get parameter missing")

    em2: Em2Comms = request.app['em2']
    try:
        await em2.check_body_signature(request_em2_node, request)
    except InvalidSignature as e:
        msg = e.args[0]
        logger.info('unauthorized em2 push msg="%s" em2-node="%s"', msg, request_em2_node)
        raise JsonErrors.HTTPUnauthorized(msg)
    return request_em2_node

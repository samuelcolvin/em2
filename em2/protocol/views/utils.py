from typing import cast

from arq import ArqRedis
from atoolbox.class_views import ExecView as _ExecView

from em2.protocol.core import Em2Comms
from em2.utils.db import conns_from_request


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.redis = cast(ArqRedis, self.redis)
        self.conns = conns_from_request(self.request)
        self.em2: Em2Comms = self.app['em2']

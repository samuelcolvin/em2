from typing import cast

from arq import ArqRedis
from atoolbox.class_views import ExecView as _ExecView, View as _View

from em2.ui.middleware import Session
from em2.utils.db import conns_from_request


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']
        self.redis = cast(ArqRedis, self.redis)
        self.conns = conns_from_request(self.request)


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']
        self.redis = cast(ArqRedis, self.redis)
        self.conns = conns_from_request(self.request)

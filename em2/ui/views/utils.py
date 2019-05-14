from typing import cast

from arq import ArqRedis
from atoolbox.class_views import ExecView as _ExecView, View as _View

from ..middleware import Session


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']
        self.redis = cast(ArqRedis, self.redis)


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']

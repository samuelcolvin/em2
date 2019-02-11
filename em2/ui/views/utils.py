from atoolbox.class_views import ExecView as _ExecView, View as _View

from ..background import push
from ..middleware import Session


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']

    async def push(self, conv_id: int, action_id: int):
        return await push(self.conn, self.redis, conv_id, action_id)

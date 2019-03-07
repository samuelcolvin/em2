from typing import List

from atoolbox.class_views import ExecView as _ExecView, View as _View

from ..background import push_all, push_multiple
from ..middleware import Session


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']

    async def push_all(self, conv_id: int):
        return await push_all(self.conn, self.app['redis'], conv_id)

    async def push_multiple(self, conv_id: int, action_ids: List[int]):
        return await push_multiple(self.conn, self.app['redis'], conv_id, action_ids)

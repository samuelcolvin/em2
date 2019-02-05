from em2.utils.web import ExecView as _ExecView, View as _View

from ..middleware import Session


class View(_View):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']


class ExecView(_ExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']

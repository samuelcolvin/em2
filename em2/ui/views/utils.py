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


def file_upload_cache_key(conv_id: int, content_id: str) -> str:
    return f'file-upload-{conv_id}-{content_id}'

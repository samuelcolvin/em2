from arq import BaseWorker

from em2.protocol.push import Push
from em2.settings import Settings


class Worker(BaseWorker):
    """
    arq worker used to execute jobs
    """

    shadows = [Push]

    def __init__(self, settings=None, **kwargs):
        self.settings = settings or Settings()
        kwargs['redis_settings'] = self.settings.redis_settings
        super().__init__(**kwargs)

    async def shadow_kwargs(self):
        return dict(
            redis_settings=self.redis_settings,
            settings=self.settings,
            worker=self,
            loop=self.loop,
            existing_redis=await self.get_redis(),
        )


def run(settings: Settings):
    from arq import RunWorkerProcess

    RunWorkerProcess('em2.worker', 'Worker')

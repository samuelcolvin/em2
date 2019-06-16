from em2 import worker


async def test_start_stop_worker(redis, settings):
    ctx = {'redis': redis, 'settings': settings}
    await worker.startup(ctx)
    keys = set(ctx.keys())
    await worker.shutdown(ctx)
    assert keys == {'settings', 'session', 'pg', 'resolver', 'conns', 'smtp_handler', 'redis'}

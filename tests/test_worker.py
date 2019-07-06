from em2 import worker


async def test_start_stop_worker(redis, settings, worker_ctx):
    ctx = {'redis': redis, 'settings': settings}
    await worker.startup(ctx)
    keys = set(ctx.keys())
    await worker.shutdown(ctx)
    assert keys == {'settings', 'client_session', 'pg', 'resolver', 'conns', 'smtp_handler', 'redis'}
    assert set(worker_ctx.keys()) == {'settings', 'client_session', 'pg', 'resolver', 'conns', 'smtp_handler', 'redis'}

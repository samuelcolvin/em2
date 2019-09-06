import json

from pytest_toolbox.comparison import AnyInt, CloseToNow

from em2.utils.web_push import web_push

from .conftest import Factory


async def test_subscribe(cli, factory: Factory, redis, web_push_sub):
    await factory.create_user()
    assert len(await redis.keys('web-push-subs:*')) == 0
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    subs = await redis.keys('web-push-subs:*')
    assert len(subs) == 1
    assert subs[0].startswith(f'web-push-subs:{factory.user.id}:')
    s = await redis.get(subs[0])
    assert json.loads(s) == web_push_sub


async def test_unsubscribe(cli, factory: Factory, redis, web_push_sub):
    await factory.create_user()
    assert len(await redis.keys('web-push-subs:*')) == 0
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1
    await cli.post_json(factory.url('ui:webpush-unsubscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 0


async def test_web_push(cli, factory: Factory, redis, worker_ctx, dummy_server, web_push_sub):
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    assert 1 == await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == ['POST /vapid/ > 201', 'POST /vapid/ > 201']
    assert len(await redis.keys('web-push-subs:*')) == 1


async def test_web_push_multiple(cli, factory: Factory, redis, worker_ctx, dummy_server, web_push_sub):
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1

    web_push_sub2 = {**web_push_sub, 'endpoint': web_push_sub['endpoint'] + '?v=1'}
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub2)
    assert len(await redis.keys('web-push-subs:*')) == 2

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    assert 2 == await web_push(worker_ctx, json.dumps(data))

    assert sorted(dummy_server.log) == [
        'POST /vapid/ > 201',
        'POST /vapid/ > 201',
        'POST /vapid/?v=1 > 201',
        'POST /vapid/?v=1 > 201',
    ]
    assert len(await redis.keys('web-push-subs:*')) == 2


async def test_web_push_unsubscribe(cli, factory: Factory, redis, dummy_server, web_push_sub):
    web_push_sub['endpoint'] = web_push_sub['endpoint'].replace('/vapid/', '/status/410/')

    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 0

    assert dummy_server.log == ['POST /status/410/ > 410']


async def test_web_push_bad(cli, factory: Factory, redis, worker_ctx, dummy_server, web_push_sub):
    web_push_sub['endpoint'] = web_push_sub['endpoint'].replace('/vapid/', '/status/500/')
    await factory.create_user()

    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub, status=500)

    assert dummy_server.log == ['POST /status/500/ > 500']
    assert len(await redis.keys('web-push-subs:*')) == 1


async def test_web_push_not_configured(cli, factory: Factory, redis, worker_ctx, dummy_server, web_push_sub):
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    worker_ctx['conns'].settings.vapid_sub_email = None
    assert 'web push not configured' == await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == ['POST /vapid/ > 201']
    assert len(await redis.keys('web-push-subs:*')) == 1


async def test_push_action(cli, factory: Factory, redis, worker, dummy_server, web_push_sub):
    user = await factory.create_user()
    conv = await factory.create_conv()
    await worker.async_run()
    assert await worker.run_check() == 1
    assert len(await redis.keys('web-push-subs:*')) == 0
    await cli.post_json(factory.url('ui:webpush-subscribe'), web_push_sub)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'actions': [{'act': 'message:add', 'body': 'this is another message'}]}
    r = await cli.post_json(factory.url('ui:act', conv=conv.key), data)
    obj = await r.json()

    await worker.async_run()
    assert await worker.run_check() == 2
    assert dummy_server.log == ['POST /vapid/ > 201', 'POST /vapid/ > 201']
    assert len(dummy_server.app['webpush']) == 2
    assert dummy_server.app['webpush'][0] == {'user_id': user.id, 'user_v': 2}
    assert dummy_server.app['webpush'][1] == {
        'conversation': conv.key,
        'interaction': obj['interaction'],
        'actions': [
            {
                'id': AnyInt(),
                'act': 'message:add',
                'ts': CloseToNow(),
                'actor': 'testing-1@example.com',
                'body': 'this is another message',
                'extra_body': False,
                'msg_format': 'markdown',
            }
        ],
        'conv_details': {
            'act': 'message:add',
            'sub': 'Test Subject',
            'email': 'testing-1@example.com',
            'creator': 'testing-1@example.com',
            'prev': 'this is another message',
            'prts': 1,
            'msgs': 2,
        },
        'user_id': user.id,
        'user_v': 3,
        'user_email': 'testing-1@example.com',
        'flags': {'inbox': 0, 'unseen': 0, 'draft': 1, 'sent': 0, 'archive': 0, 'all': 1, 'spam': 0, 'deleted': 0},
    }

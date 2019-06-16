import json

import pytest
from atoolbox import RequestError

from em2.utils.web_push import web_push

from .conftest import Factory

sub_info = {'endpoint': 'https://example.com/token', 'expirationTime': None, 'keys': {'p256dh': 'foo', 'auth': 'bar'}}


async def test_subscribe(cli, factory: Factory, redis):
    await factory.create_user()
    assert len(await redis.keys('web-push-subs:*')) == 0
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    subs = await redis.keys('web-push-subs:*')
    assert len(subs) == 1
    assert subs[0] == f'web-push-subs:{factory.user.id}'
    members = await redis.smembers(subs[0])
    assert len(members) == 1
    m = json.loads(members[0])
    assert m == sub_info


async def test_unsubscribe(cli, factory: Factory, redis):
    await factory.create_user()
    assert len(await redis.keys('web-push-subs:*')) == 0
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1
    await cli.post_json(factory.url('ui:webpush-unsubscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 0


async def test_web_push(cli, factory: Factory, redis, worker_ctx, dummy_server):
    sub_info = {
        'endpoint': dummy_server.server_name.replace('localhost', '127.0.0.1') + '/status/201/',
        'expirationTime': None,
        'keys': {
            'p256dh': 'BJpYv7NU1pjT3T-le_0Zv57LW9cAHRshK3NaMg6Kl412ngTcybNMQw9jvFHEpqq8Sc2oxN382vkSfZiV2ul_CLQ',
            'auth': '9z4xquuNpVxHOdBnSGkvSw',
        },
    }
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    assert 1 == await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == ['POST status/201']
    assert len(await redis.keys('web-push-subs:*')) == 1


async def test_web_push_unsubscribe(cli, factory: Factory, redis, worker_ctx, dummy_server):
    sub_info = {
        'endpoint': dummy_server.server_name.replace('localhost', '127.0.0.1') + '/status/410/',
        'expirationTime': None,
        'keys': {
            'p256dh': 'BJpYv7NU1pjT3T-le_0Zv57LW9cAHRshK3NaMg6Kl412ngTcybNMQw9jvFHEpqq8Sc2oxN382vkSfZiV2ul_CLQ',
            'auth': '9z4xquuNpVxHOdBnSGkvSw',
        },
    }
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    assert 1 == await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == ['POST status/410']
    assert len(await redis.keys('web-push-subs:*')) == 0


async def test_web_push_bad(cli, factory: Factory, redis, worker_ctx, dummy_server):
    sub_info = {
        'endpoint': dummy_server.server_name.replace('localhost', '127.0.0.1') + '/status/500/',
        'expirationTime': None,
        'keys': {
            'p256dh': 'BJpYv7NU1pjT3T-le_0Zv57LW9cAHRshK3NaMg6Kl412ngTcybNMQw9jvFHEpqq8Sc2oxN382vkSfZiV2ul_CLQ',
            'auth': '9z4xquuNpVxHOdBnSGkvSw',
        },
    }
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    with pytest.raises(RequestError):
        await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == ['POST status/500']
    assert len(await redis.keys('web-push-subs:*')) == 1


async def test_web_push_not_configured(cli, factory: Factory, redis, worker_ctx, dummy_server):
    sub_info = {
        'endpoint': dummy_server.server_name.replace('localhost', '127.0.0.1') + '/status/201/',
        'expirationTime': None,
        'keys': {
            'p256dh': 'BJpYv7NU1pjT3T-le_0Zv57LW9cAHRshK3NaMg6Kl412ngTcybNMQw9jvFHEpqq8Sc2oxN382vkSfZiV2ul_CLQ',
            'auth': '9z4xquuNpVxHOdBnSGkvSw',
        },
    }
    await factory.create_user()
    await cli.post_json(factory.url('ui:webpush-subscribe'), sub_info)
    assert len(await redis.keys('web-push-subs:*')) == 1

    data = {'participants': [{'user_id': factory.user.id, 'foo': 'bar'}], 'other': 42}
    worker_ctx['conns'].settings.vapid_sub_email = None
    assert 'web push not configured' == await web_push(worker_ctx, json.dumps(data))

    assert dummy_server.log == []
    assert len(await redis.keys('web-push-subs:*')) == 1

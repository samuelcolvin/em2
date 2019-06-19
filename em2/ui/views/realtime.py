import logging
from asyncio import CancelledError

from aiohttp import WSMsgType
from aiohttp.web_exceptions import HTTPNotImplemented
from aiohttp.web_ws import WebSocketResponse
from atoolbox import JsonErrors

from em2.background import Background
from em2.utils.web_push import SubscriptionModel, subscribe, unsubscribe

from ..middleware import WsReauthenticate, load_session
from .utils import ExecView

logger = logging.getLogger('em2.ui.realtime')


async def websocket(request):
    ws = WebSocketResponse()

    try:
        session = await load_session(request)
    except (JsonErrors.HTTPUnauthorized, WsReauthenticate) as exc:
        await ws.prepare(request)
        try:
            await ws.close(code=4401 if isinstance(exc, WsReauthenticate) else 4403)
        except CancelledError:
            # happens, not a problem
            pass
        return ws

    logger.debug('ws connection user=%s', session.user_id)
    await ws.prepare(request)

    pg = request.app['pg']
    json_obj = await pg.fetchval("select json_build_object('user_v', v) from users where id=$1", session.user_id)
    await ws.send_str(json_obj)

    background: Background = request.app['background']
    background.add_ws(session.user_id, ws)

    # could update
    try:
        async for msg in ws:
            if msg.tp == WSMsgType.ERROR:
                logger.warning('ws connection closed with exception %s', ws.exception())
                break
            else:
                logger.warning('unknown ws message, %r: %r', msg.tp, msg.data)
    except CancelledError:
        # happens, regularly, not a problem
        pass
    finally:
        logger.debug('ws disconnection user=%s', session.user_id)
        background.remove_ws(session.user_id, ws)
    return ws


class WebPushSubscribe(ExecView):
    Model = SubscriptionModel

    async def execute(self, m: Model):
        if not self.settings.vapid_private_key or not self.settings.vapid_sub_email:
            raise HTTPNotImplemented(text="vapid_private_key and vapid_sub_email must be set")
        await subscribe(self.conns, self.app['http_client'], m, self.session.user_id)


class WebPushUnsubscribe(ExecView):
    Model = SubscriptionModel

    async def execute(self, m: Model):
        await unsubscribe(self.conns, m, self.session.user_id)

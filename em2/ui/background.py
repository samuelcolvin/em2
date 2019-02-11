import asyncio
import json
import logging
from asyncio import CancelledError
from typing import Dict

from aiohttp.web_ws import WebSocketResponse
from aioredis import Redis
from buildpg.asyncpg import BuildPgConnection

from em2.settings import Settings

logger = logging.getLogger('em2.ui.background')
channel_name = 'actions'


class Background:
    def __init__(self, app):
        self.app = app
        self.settings: Settings = app['settings']
        self.connections: Dict[int, WebSocketResponse] = {}
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._run())

    def add_ws(self, user_id: int, ws: WebSocketResponse):
        self.connections[user_id] = ws

    def remove_ws(self, user_id: int):
        self.connections.pop(user_id)

    async def _run(self):
        logger.info('starting background task')
        try:
            with await self.app['redis'] as self.redis:
                channel, *_ = await self.redis.psubscribe(channel_name)
                while await channel.wait_message():
                    _, msg = await channel.get()
                    await self.process_action(msg)
        except CancelledError:
            # happens, not a problem
            logger.info('background task got cancelled')
        except Exception as exc:
            logger.exception('exception in background task, %s: %s', exc.__class__.__name__, exc)
            raise

    async def process_action(self, msg: bytes):
        if self.connections:
            data = json.loads(msg)
            user_ids = set(data['user_ids'])
            msg = msg.decode()
            await asyncio.gather(*[self.send(user_id, msg) for user_id in user_ids.intersection(self.connections)])

    async def send(self, user_id: int, msg: str):
        ws = self.connections[user_id]
        try:
            await ws.send_str(msg)
        except (RuntimeError, AttributeError):
            logger.info('websocket "%s" closed (user id %d), removing', ws, user_id)
            self.connections.pop(user_id)


# TODO this might not include enough info, eg. won't be enough when publishing or creating a conv
push_sql = """
select json_strip_nulls(json_build_object(
  'conv_key', conv_key,
  'user_ids', array_to_json(array[a.actor_id] || participants),
  'id', id,
  'act', act,
  'ts', ts,
  'actor', actor,
  'body', body,
  'msg_format', msg_format,
  'participant', participant,
  'follows', follows,
  'msg_parent', msg_parent
))
from (
  select a.id as id, a.act as act, a.ts as ts, actor_user.email as actor,
  a.body as body, a.msg_format as msg_format,
  prt_user.email as participant, follows_action.id as follows, parent_action.id as msg_parent,
  c.key as conv_key, a.actor as actor_id
  from actions as a

  join users as actor_user on a.actor = actor_user.id
  join conversations as c on a.conv = c.id

  left join users as prt_user on a.participant_user = prt_user.id
  left join actions as follows_action on a.follows = follows_action.pk
  left join actions as parent_action on a.msg_parent = parent_action.pk
  where a.conv=$1 and a.id=$2
) as a,
(
  select array_agg(t.user_id) as participants
  from (
    select user_id
    from participants
    join conversations as c on participants.conv = c.id
    where conv=$1 and c.published=true
  ) as t
) as participants
"""


async def push(pg_conn: BuildPgConnection, redis: Redis, conv_id: int, action_id: int):
    data = await pg_conn.fetchval(push_sql, conv_id, action_id)
    await redis.publish(channel_name, data)

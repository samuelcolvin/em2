import asyncio
import logging
from asyncio import CancelledError
from typing import Any, Dict, List, Optional

import ujson
from aiohttp.abc import Application
from aiohttp.web_ws import WebSocketResponse
from arq.connections import ArqRedis

from em2.core import Connections, get_flag_counts
from em2.settings import Settings

logger = logging.getLogger('em2.ui.background')


class Background:
    def __init__(self, app: Application):
        self.app = app
        self.settings: Settings = app['settings']
        self.connections: Dict[int, List[WebSocketResponse]] = {}
        self.loop = asyncio.get_event_loop()
        self.loop.create_task(self._run())
        self.conns = Connections(self.app['pg'], self.app['redis'], self.settings)

    def add_ws(self, user_id: int, ws: WebSocketResponse):
        if user_id in self.connections:
            self.connections[user_id].append(ws)
        else:
            self.connections[user_id] = [ws]

    def remove_ws(self, user_id: int, ws: WebSocketResponse):
        wss = self.connections[user_id]
        wss.remove(ws)
        if not wss:
            self.connections.pop(user_id)

    async def _run(self):
        logger.info('starting background task')
        try:
            with await self.app['redis'] as self.redis:
                channel, *_ = await self.redis.psubscribe(channel_name(self.redis))
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
            data = ujson.loads(msg)
            coros = []
            participants = data.pop('participants')
            # hack to avoid building json for every user, remove the ending "}" so extra json can be appended
            msg_json_chunk = ujson.dumps(data)[:-1]
            for p in participants:
                user_id = p['user_id']
                wss = self.connections.get(user_id)
                if wss is not None:
                    coros.append(self.send(user_id, p, wss, msg_json_chunk))

            await asyncio.gather(*coros)

    async def send(self, user_id: int, participant: dict, wss: List[WebSocketResponse], msg_json_chunk: str):
        participant['flags'] = await get_flag_counts(self.conns, user_id)
        msg = msg_json_chunk + ',' + ujson.dumps(participant)[1:]
        for ws in wss:
            try:
                await ws.send_str(msg)
            except (RuntimeError, AttributeError):
                logger.info('websocket "%s" closed (user id %d), removing', ws, user_id)
                self.remove_ws(user_id, ws)


def channel_name(redis: ArqRedis):
    return f'actions-{redis.db}'


local_users_sql = """
select json_build_object(
  'participants', participants,
  'conv_details', conv_details
)
from (
  select array_to_json(array_agg(json_strip_nulls(row_to_json(t)))) as participants
  from (
    select p.user_id, p.spam, p.label_ids as labels, u.v user_v, u.email user_email
    from participants as p
    join conversations as c on p.conv = c.id
    join users as u on p.user_id = u.id
    where conv=$1
      and (c.publish_ts is not null or p.user_id=c.creator)
      and (u.user_type = 'new' or u.user_type = 'local')
  ) as t
) as participants,
(
  select details as conv_details from conversations where id=$1
) as conv_details
"""


async def _push_local(conns: Connections, conv_id: int, actions_data: str, interaction_id: Optional[str]):
    extra = await conns.main.fetchval(local_users_sql, conv_id)
    extra_json = f',"interaction_id": "{interaction_id}",' if interaction_id else ','
    actions_data_extra = actions_data[:-1] + extra_json + extra[1:]
    await conns.redis.publish(channel_name(conns.redis), actions_data_extra)
    await conns.redis.enqueue_job('web_push', actions_data_extra)


remote_users_sql = """
select u.email, u.user_type
from participants as p
join conversations as c on p.conv = c.id
join users as u on p.user_id = u.id
where conv=$1 and c.publish_ts is not null and u.user_type != 'local'
"""


async def _push_remote(conns: Connections, conv_id: int, actions_data: str, **extra: Any):
    remote_users = [tuple(r) for r in await conns.main.fetch(remote_users_sql, conv_id)]
    if remote_users:
        await conns.redis.enqueue_job('push_actions', actions_data, remote_users, **extra)


push_sql_template = """
select json_build_object(
  'actions', actions,
  'conversation', conversation
)
from (
  select array_to_json(array_agg(json_strip_nulls(row_to_json(t)))) as actions
  from (
    select a.id, a.act, a.ts, actor_user.email actor,
    left(a.body, 1024) body,
    case when a.body is null then null else length(a.body) > 1024 end extra_body,
    a.msg_format, a.warnings,
    prt_user.email participant, follows_action.id follows, parent_action.id parent,
    (select array_agg(row_to_json(f))
      from (
        select content_disp, hash, content_id, name, content_type, size
        from files
        where files.action = a.pk
        order by content_id  -- TODO only used in tests I think, could be removed
      ) f
    ) as files
    from actions as a

    join users as actor_user on a.actor = actor_user.id
    join conversations as c on a.conv = c.id

    left join users as prt_user on a.participant_user = prt_user.id
    left join actions as follows_action on a.follows = follows_action.pk
    left join actions as parent_action on a.parent = parent_action.pk
    {}
  ) as t
) actions, (
  select key conversation from conversations where id=$1
) conversation
"""

push_sql_all = push_sql_template.format('where a.conv=$1 order by a.id')
push_sql_multiple = push_sql_template.format('where a.conv=$1 and a.id=any($2)')


async def push_all(conns: Connections, conv_id: int, *, transmit=True, **extra: Any):
    # FIXME: rename these to notify*?
    actions_data = await conns.main.fetchval(push_sql_all, conv_id)
    await _push_local(conns, conv_id, actions_data, None)
    if transmit:
        await _push_remote(conns, conv_id, actions_data, **extra)


async def push_multiple(
    conns: Connections,
    conv_id: int,
    action_ids: List[int],
    *,
    transmit: bool = True,
    interaction_id: str = None,
    **extra: Any,
):
    actions_data = await conns.main.fetchval(push_sql_multiple, conv_id, action_ids)
    await _push_local(conns, conv_id, actions_data, interaction_id)
    if transmit:
        if interaction_id:
            extra['interaction_id'] = interaction_id
        await _push_remote(conns, conv_id, actions_data, **extra)

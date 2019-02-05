from datetime import datetime
from typing import List, Set

from atoolbox import JsonErrors, raw_json_response
from buildpg import V, funcs
from pydantic import BaseModel, EmailStr, constr

from em2.core import MsgFormat, draft_conv_key, generate_conv_key, get_create_multiple_users

from .utils import ExecView, View


class ConvList(View):
    # TODO add count (max 999)
    sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select c.key as key, c.subject as subject, c.created_ts as created_ts, c.updated_ts as updated_ts,
        c.published as published, c.snippet as snippet
      from conversations as c
      left join participants on c.id = participants.conv
      where participants.user_id=$1
      order by c.created_ts, c.id desc
      limit 50
    ) t;
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id)
        return raw_json_response(raw_json or '[]')


class ConvActions(View):
    get_conv_sql = """
    select c.id, c.published, c.creator from conversations as c
    join participants as p on c.id=p.conv
    where p.user_id=$1 and c.key like $2
    order by c.created_ts desc
    limit 1
    """
    # used when the user was part of the conversation, but got removed
    get_conv_was_deleted_sql = """
    select c.id, c.published, c.creator, a.id from actions as a
    join conversations as c on a.conv = c.id
    where a.user=$1 and c.key like $2 and a.component='participant' and a.verb='delete'
    order by c.created_ts desc, a.id desc
    limit 1
    """

    actions_sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select a.key as key, a.verb as verb, a.component as component, a.body as body, a.timestamp as timestamp,
      actor_user.email as actor,
      a_parent.key as parent,
      m.key as message,
      prt_user.email as participant
      from actions as a

      left join actions as a_parent on a.parent = a_parent.id
      left join messages as m on a.message = m.id

      join users as actor_user on a.actor = actor_user.id

      left join users as prt_user on a.user = prt_user.id
      where :where
      order by a.id
    ) t;
    """

    action_id_sql = 'select id from actions where conv=$1 and key=$2'

    async def call(self):
        conv_key = self.request.match_info['conv'] + '%'
        r = await self.conn.fetchrow(self.get_conv_sql, self.session.user_id, conv_key + '%')
        where_logic: List[V] = []
        if r:
            conv_id, published, creator = r
        else:
            # can happen legitimately when they were deleted from the conversation
            conv_id, published, creator, last_action = await self.fetchrow404(
                self.get_conv_was_deleted_sql, self.session.user_id, conv_key + '%'
            )
            where_logic.append(V('a.id') <= last_action)

        if not published and self.session.user_id != creator:
            raise JsonErrors.HTTPForbidden(error='conversation is unpublished and you are not the creator')

        since_action = self.request.query.get('since')
        if since_action:
            first_action_id = await self.fetchval404(self.action_id_sql, conv_id, since_action)
            where_logic.append(V('a.id') > first_action_id)

        where_logic.append(V('a.conv') == conv_id)
        json_str = await self.conn.fetchval_b(self.actions_sql, where=funcs.AND(*where_logic))
        return raw_json_response(json_str or '[]')


class ConvCreate(ExecView):
    class Model(BaseModel):
        subject: constr(max_length=255, strip_whitespace=True)
        message: constr(max_length=2047, strip_whitespace=True)
        participants: Set[EmailStr] = set()
        msg_format: MsgFormat = MsgFormat.markdown
        publish = False

    async def execute(self, conv: Model):
        ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.email, ts, conv.subject) if conv.publish else draft_conv_key()
        creator_id = self.session.user_id
        async with self.conn.transaction():
            conv_id = await self.conn.fetchval(
                """
                insert into conversations (key, creator, subject, published, created_ts, updated_ts)
                values                    ($1,  $2,      $3,      $4       , $5        , $5        )
                on conflict (key) do nothing
                returning id
                """,
                conv_key,
                creator_id,
                conv.subject,
                conv.publish,
                ts,
            )
            if conv_id is None:
                raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')

            part_users = await get_create_multiple_users(self.conn, conv.participants)
            user_ids = [creator_id] + list(part_users.values())

            await self.conn.execute(
                """
                with parts as (
                  insert into participants (conv, user_id) (select $1, unnest ($2::int[])) returning id as p
                )
                insert into actions (conv, verb, component, actor, participant) (
                  select $1, 'add', 'participant', $3, p from parts
                )
                """,
                conv_id,
                user_ids,
                creator_id,
            )
            await self.conn.execute(
                """
                insert into actions (conv, verb , component, actor, body, msg_format)
                values              ($1,   'add', 'message', $2   , $3  , $4)
                """,
                conv_id,
                creator_id,
                conv.message,
                conv.msg_format,
            )
            publish_id = None
            if conv.publish:
                publish_id = await self.conn.fetchrow(
                    """
                    insert into actions (conv, verb    , component, actor, ts)
                    values              ($1,  'publish', 'conv'   , $2   , $3)
                    returning id
                    """,
                    conv_id,
                    creator_id,
                    ts,
                )
                await self.conn.execute('update actions set ts=$2 where conv=$1', conv_id, ts)

        print(publish_id)
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)

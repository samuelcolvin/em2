from datetime import datetime
from typing import Set

from atoolbox import JsonErrors, parse_request_query, raw_json_response
from pydantic import BaseModel, EmailStr, constr

from em2.core import (
    ActionModel,
    ActionsTypes,
    MsgFormat,
    act,
    conv_actions_json,
    draft_conv_key,
    generate_conv_key,
    get_conv_for_user,
    get_create_multiple_users,
)

from .utils import ExecView, View


class ConvList(View):
    # TODO add count (max 999)
    sql = """
    select array_to_json(array_agg(row_to_json(t)), true)
    from (
      select key, created_ts, updated_ts, published, details
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
    class QueryModel(BaseModel):
        since: int = None

    async def call(self):
        m = parse_request_query(self.request, self.QueryModel)
        json_str = await conv_actions_json(self.conn, self.session.user_id, self.request.match_info['conv'], m.since)
        return raw_json_response(json_str)


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
                insert into conversations (key, creator, published, created_ts, updated_ts)
                values                    ($1,  $2     , $3       , $4        , $4        )
                on conflict (key) do nothing
                returning id
                """,
                conv_key,
                creator_id,
                conv.publish,
                ts,
            )
            if conv_id is None:
                raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')

            part_users = await get_create_multiple_users(self.conn, conv.participants)
            user_ids = [creator_id] + list(part_users.values())

            await self.conn.execute(
                'insert into participants (conv, user_id) (select $1, unnest($2::int[]))', conv_id, user_ids
            )
            await self.conn.execute(
                """
                insert into actions (conv, act             , actor, ts, participant_user) (
                  select             $1  , 'participant:add', $2  , $3, unnest($4::int[])
                )
                """,
                conv_id,
                creator_id,
                ts,
                user_ids,
            )
            await self.conn.execute(
                """
                insert into actions (conv, act          , actor, ts, body, msg_format)
                values              ($1  , 'message:add', $2   , $3, $4  , $5)
                """,
                conv_id,
                creator_id,
                ts,
                conv.message,
                conv.msg_format,
            )
            publish_id = await self.conn.fetchrow(
                """
                insert into actions (conv, act, actor, ts, body)
                values              ($1  , $2 , $3   , $4, $5)
                returning id
                """,
                conv_id,
                ActionsTypes.conv_publish if conv.publish else ActionsTypes.conv_create,
                creator_id,
                ts,
                conv.subject,
            )

        assert publish_id
        # await self.pusher.push(create_action_id, actor_only=True)
        return dict(key=conv_key, status_=201)


class ConvAct(ExecView):
    Model = ActionModel

    async def execute(self, action: Model):
        # TODO perhaps this logic could be shared with protocol?
        conv_id, last_action = await get_conv_for_user(self.conn, self.session.user_id, self.request.match_info['conv'])
        if last_action:
            raise JsonErrors.HTTPNotFound(message='Conversation not found')

        action_id = await act(self.conn, self.settings, self.session.user_id, self.request.match_info['conv'], action)
        assert action_id

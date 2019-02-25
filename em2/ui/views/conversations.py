from datetime import datetime
from typing import Any, Dict, List

from atoolbox import JsonErrors, get_offset, parse_request_query, raw_json_response
from pydantic import BaseModel, EmailStr, constr, validator

from em2.core import (
    ActionModel,
    ActionsTypes,
    MsgFormat,
    act,
    construct_conv,
    conv_actions_json,
    draft_conv_key,
    generate_conv_key,
    get_conv_for_user,
    get_create_multiple_users,
    max_participants,
    update_conv_users,
)

from .utils import ExecView, View


class ConvList(View):
    sql = """
    select json_build_object(
      'count', count,
      'conversations', conversations
    ) from (
      select count(*) from conversations as c
        join participants as p on c.id = p.conv
        where p.user_id=$1
        limit 999
    ) as count, (
      select coalesce(array_to_json(array_agg(row_to_json(t)), true), '[]') as conversations
      from (
        select key, created_ts, updated_ts, publish_ts, last_action_id, p.seen as seen, details
        from conversations as c
        join participants as p on c.id = p.conv
        where p.user_id=$1 and (publish_ts is not null or creator=$1)
        order by c.created_ts, c.id desc
        limit 50
        offset $2
      ) t
    ) as conversations
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id, get_offset(self.request, paginate_by=50))
        return raw_json_response(raw_json)


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
        message: constr(max_length=10000, strip_whitespace=True)
        msg_format: MsgFormat = MsgFormat.markdown
        publish = False

        class Participants(BaseModel):
            email: EmailStr
            name: str = None

        participants: List[Participants] = []

        @validator('participants', whole=True)
        def check_participants_count(cls, v):
            if len(v) > max_participants:
                raise ValueError(f'no more than {max_participants} participants permitted')
            return v

    async def execute(self, conv: Model):
        ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.email, ts, conv.subject) if conv.publish else draft_conv_key()
        creator_id = self.session.user_id
        async with self.conn.transaction():
            conv_id = await self.conn.fetchval(
                """
                insert into conversations (key, creator, publish_ts, created_ts, updated_ts)
                values                    ($1,  $2     , $3        , $4        , $4        )
                on conflict (key) do nothing
                returning id
                """,
                conv_key,
                creator_id,
                ts if conv.publish else None,
                ts,
            )
            if conv_id is None:
                raise JsonErrors.HTTPConflict(error='key conflicts with existing conversation')

            # TODO currently only email is used
            participants = set(p.email for p in conv.participants)
            part_users = await get_create_multiple_users(self.conn, participants)

            await self.conn.execute(
                'insert into participants (conv, user_id, seen) (select $1, $2, true)', conv_id, creator_id
            )
            other_user_ids = list(part_users.values())
            await self.conn.execute(
                'insert into participants (conv, user_id) (select $1, unnest($2::int[]))', conv_id, other_user_ids
            )
            user_ids = [creator_id] + other_user_ids
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
            await self.conn.execute(
                """
                insert into actions (conv, act, actor, ts, body)
                values              ($1  , $2 , $3   , $4, $5)
                """,
                conv_id,
                ActionsTypes.conv_publish if conv.publish else ActionsTypes.conv_create,
                creator_id,
                ts,
                conv.subject,
            )
            await update_conv_users(self.conn, conv_id)

        await self.push_all(conv_id)
        return dict(key=conv_key, status_=201)


class ConvAct(ExecView):
    class Model(BaseModel):
        actions: List[ActionModel]

    async def execute(self, m: Model):
        conv_prefix = self.request.match_info['conv']
        action_ids = []
        conv_id = None
        async with self.conn.transaction():
            for action in m.actions:
                conv_id, action_id = await act(self.conn, self.settings, self.session.user_id, conv_prefix, action)
                action_id and action_ids.append(action_id)
        if action_ids:
            await self.push_multiple(conv_id, action_ids)
        return {'action_ids': action_ids}


class ConvPublish(ExecView):
    class Model(BaseModel):
        publish: bool

        @validator('publish')
        def check_publish(cls, v):
            if not v:
                raise ValueError('publish must be true')
            return v

    async def execute(self, action: Model):
        conv_prefix = self.request.match_info['conv']
        conv_id, _ = await get_conv_for_user(self.conn, self.session.user_id, conv_prefix, req_pub=False)

        # could do more efficiently than this, but would require duplicate logic
        conv_summary = await construct_conv(self.conn, self.session.user_id, conv_prefix)

        ts = datetime.utcnow()
        conv_key = generate_conv_key(self.session.email, ts, conv_summary['subject'])
        async with self.conn.transaction():
            async with self.conn.transaction():
                # this is a hard check that conversations can't be published multiple times,
                # "for no key update" locks the row during this transaction
                publish_ts = await self.conn.fetchval(
                    'select publish_ts from conversations where id=$1 for no key update', conv_id
                )
                # this prevents a race condition if ConvPublish is called concurrently
                if publish_ts:
                    raise JsonErrors.HTTPBadRequest('Conversation already published')
                await self.conn.execute(
                    'update conversations set publish_ts=current_timestamp, last_action_id=0, key=$2 where id=$1',
                    conv_id,
                    conv_key,
                )

            # TODO, maybe in future we'll need a record of these old actions?
            await self.conn.execute('delete from actions where conv=$1', conv_id)

            await self.conn.execute(
                """
                insert into actions (conv, act, actor, ts, participant_user)
                (select $1, 'participant:add', $2, $3, user_id from participants where conv=$1)
                """,
                conv_id,
                self.session.user_id,
                ts,
            )
            for msg in conv_summary['messages']:
                await self.add_msg(msg, conv_id, ts)

            await self.conn.execute(
                """
                insert into actions (conv, act           , actor, ts, body)
                values              ($1  , 'conv:publish', $2   , $3, $4)
                """,
                conv_id,
                self.session.user_id,
                ts,
                conv_summary['subject'],
            )
            await update_conv_users(self.conn, conv_id)
        await self.push_all(conv_id)
        return dict(key=conv_key)

    async def add_msg(self, msg_info: Dict[str, Any], conv_id: int, ts: datetime, parent: int = None):
        """
        Recursively create messages.
        """
        pk = await self.conn.fetchval(
            """
            insert into actions (conv, act          , actor, ts, body, msg_format, parent)
            values              ($1  , 'message:add', $2   , $3, $4  , $5        , $6)
            returning pk
            """,
            conv_id,
            self.session.user_id,
            ts,
            msg_info['body'],
            msg_info['format'],
            parent,
        )
        for msg in msg_info.get('children', []):
            await self.add_msg(msg, conv_id, ts, pk)

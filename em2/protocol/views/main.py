import asyncio
import logging
from datetime import datetime
from itertools import groupby
from operator import attrgetter
from typing import Any, List, Optional

import nacl.encoding
from atoolbox import JsonErrors, json_response
from pydantic import BaseModel, EmailStr, conint, constr, validator

from em2.core import (
    ActionTypes,
    ConvCreateMessage,
    UserTypes,
    apply_actions,
    create_conv,
    follow_action_types,
    get_create_multiple_users,
    get_create_user,
    participant_action_types,
)
from em2.protocol.core import InvalidSignature
from em2.utils.core import MsgFormat

from .utils import ExecView

logger = logging.getLogger('em2.protocol.views')


async def signing_verification(request):
    # TODO this could be cached if called a lot
    return json_response(
        keys=[
            {
                'key': request.app['signing_key'].verify_key.encode(encoder=nacl.encoding.HexEncoder).decode(),
                'ttl': 86400,
            }
        ]
    )


with_body_actions = {ActionTypes.msg_add, ActionTypes.msg_modify, ActionTypes.subject_modify, ActionTypes.conv_publish}


class Action(BaseModel):
    id: conint(gt=0)  # TODO check that ID increments correctly
    act: ActionTypes
    ts: datetime
    actor: EmailStr
    body: Optional[constr(min_length=1, max_length=10000, strip_whitespace=True)] = None
    extra_body: bool = False
    participant: Optional[EmailStr] = None
    msg_format: MsgFormat = MsgFormat.markdown
    follows: Optional[int] = None
    parent: Optional[int] = None
    warnings: Any = None  # TODO stricter type
    files: list = None  # TODO stricter type

    @validator('participant', always=True)
    def check_participant(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and not v and act in participant_action_types:
            raise ValueError('participant is required for participant actions')
        if act and v and act not in participant_action_types:
            raise ValueError('participant must be omitted except for participant actions')
        return v

    @validator('body', always=True)
    def check_body(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and v is None and act in with_body_actions:
            raise ValueError('body is required for message:add, message:modify and subject:modify')
        if act and v is not None and act not in with_body_actions:
            raise ValueError('body must be omitted except for message:add, message:modify and subject:modify')
        return v

    @validator('follows', always=True)
    def check_follows(cls, v, values):
        act: ActionTypes = values.get('act')
        if act and v is None and act in follow_action_types:
            raise ValueError('follows is required for this action')
        return v


class Em2Push(ExecView):
    """
    Currently:
    * 200 means ok
    * 400 errors are permanent
    * 401 errors might be temporary
    * 470 specifically means retry with more information
    * everything else should be retried

    Need to formalise this.
    """

    class Model(BaseModel):
        em2_node: constr(min_length=4)
        conversation: str
        actions: List[Action]

    async def execute(self, m: Model):
        try:
            await self.em2.check_signature(m.em2_node, self.request)
        except InvalidSignature as e:
            msg = e.args[0]
            logger.info('unauthorized em2 push msg="%s" em2-node="%s"', msg, m.em2_node)
            raise JsonErrors.HTTPUnauthorized()

        last_action = m.actions[-1]
        if last_action.act == ActionTypes.conv_publish:
            await self.published_conv(last_action, m)
        else:
            await self.append_to_conversation(m)

    async def published_conv(self, publish_action: Action, m: Model):
        """
        New conversation just published
        """
        actions = [a for a in m.actions if a.id <= publish_action.id]
        if not all(a.actor == publish_action.actor for a in actions):
            raise JsonErrors.HTTPBadRequest('publishing conversation, but multiple actors')

        actor_email = publish_action.actor
        actor_node = await self.em2.get_em2_node(actor_email)
        if m.em2_node != actor_node:
            msg = 'actor does not have em2 node' if actor_node is None else 'actor does not match em2 node'
            raise JsonErrors.HTTPBadRequest(msg)

        messages = []
        participants = {}
        for a in actions:
            if a.act == ActionTypes.msg_add:
                messages.append(
                    ConvCreateMessage(body=a.body, msg_format=a.msg_format, action_id=a.id, parent=a.parent)
                )
            elif a.act == ActionTypes.prt_add and a.participant != actor_email:
                participants[a.participant] = a.id

        actor_id = await get_create_user(self.conns, actor_email, UserTypes.remote_em2)
        await create_conv(
            conns=self.conns,
            creator_email=actor_email,
            creator_id=actor_id,
            subject=publish_action.body,
            publish=True,
            messages=messages,
            participants=participants,
            ts=publish_action.ts,
            given_conv_key=m.conversation,
            leader_node=m.em2_node,
        )

    async def append_to_conversation(self, m: Model):
        actor_emails = {a.actor for a in m.actions}
        nodes = set(await asyncio.gather(*[self.em2.get_em2_node(e) for e in actor_emails]))
        if None in nodes:
            raise JsonErrors.HTTPBadRequest("not all actors' have an em2 nodes")
        if nodes != {m.em2_node}:
            raise JsonErrors.HTTPBadRequest("not all actors' em2 node match request node")

        publish_action = next((a for a in m.actions if a.act == ActionTypes.conv_publish), None)
        r = await self.conns.main.fetchrow(
            'select id, last_action_id, leader_node from conversations where key=$1', m.conversation
        )
        if not r:
            if publish_action:
                # conversation doesn't exist and we have the publish action, create the conversation, then apply
                # extra actions
                await self.published_conv(publish_action, m)
                actions_to_apply = [a for a in m.actions if a.id > publish_action.id]
                conv_ref = m.conversation
            else:
                # conversation doesn't exist and there's no publish_action, need the whole conversation
                raise JsonErrors.HTTP470('full conversation required')  # TODO better error
        else:
            conv_ref, last_action_id, leader_node = r
            if leader_node != m.em2_node:
                raise JsonErrors.HTTPBadRequest('request em2 node does not match current em2 node')

            if last_action_id + 1 < m.actions[0].id:
                raise JsonErrors.HTTP470('full conversation required')  # TODO better error

            actions_to_apply = [a for a in m.actions if a.id > last_action_id]
            if not actions_to_apply:
                raise JsonErrors.HTTPBadRequest('no new actions to apply')

        actor_user_ids = await get_create_multiple_users(self.conns, actor_emails)
        for actor_email, actions_gen in groupby(actions_to_apply, attrgetter('actor')):
            # TODO files
            await apply_actions(self.conns, actor_user_ids[actor_email], conv_ref, list(actions_gen))

from datetime import datetime
from typing import Any, List, Optional

import nacl.encoding
from atoolbox import JsonErrors, json_response
from pydantic import BaseModel, EmailStr, conint, constr, validator

from em2.core import (
    ActionTypes,
    ConvCreateMessage,
    UserTypes,
    create_conv,
    follow_action_types,
    get_create_user,
    participant_action_types,
)
from em2.protocol.core import InvalidSignature
from em2.utils.core import MsgFormat

from .utils import ExecView


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
    class Model(BaseModel):
        em2_node: str
        conversation: str
        actions: List[Action]

    async def execute(self, m: Model):
        try:
            await self.em2.check_signature(m.em2_node, self.request)
        except InvalidSignature as e:
            raise JsonErrors.HTTPForbidden(e.args[0])

        last_action = m.actions[-1]
        if last_action.act == ActionTypes.conv_publish:
            await self.published_conv(last_action, m)
        else:
            raise NotImplementedError('TODO')

    async def published_conv(self, publish_action: Action, m: Model):
        """
        New conversation just published
        """
        if not all(a.actor == publish_action.actor for a in m.actions):
            raise JsonErrors.HTTPBadRequest('publishing conversation, but multiple actors')

        actor_email = publish_action.actor
        actor_node = await self.em2.get_em2_node(actor_email)
        if m.em2_node != actor_node:
            raise JsonErrors.HTTPBadRequest(
                'actor does not match em2 node', details={'actor_node': actor_node, 'request_node': m.em2_node}
            )

        messages = []
        participants = {}
        for a in m.actions:
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
        )

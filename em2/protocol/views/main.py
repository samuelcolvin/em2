from datetime import datetime
from typing import Any, List, Optional

import nacl.encoding
from atoolbox import ExecView, json_response
from pydantic import EmailStr, constr, validator

from em2.core import ActionModel, ActionTypes, follow_action_types, participant_action_types, with_body_actions
from em2.utils.core import MsgFormat


async def signing_verification(request):
    # TODO this could be cached if called a lot
    return json_response(
        list_=[
            {
                'key': request.app['signing_key'].verify_key.encode(encoder=nacl.encoding.HexEncoder).decode(),
                'ttl': 86400,
            }
        ]
    )


class Action(ActionModel):
    id: int
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
    class Model:
        platform: str
        conversation: str
        actions: List[Action]

    async def execute(self, m: Model):
        # debug(m)
        pass

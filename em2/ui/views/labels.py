from enum import Enum

from atoolbox import JsonErrors, parse_request_query, raw_json_response
from atoolbox.bread import Bread
from buildpg import V
from buildpg.clauses import Where
from pydantic import BaseModel, constr

from em2.core import get_conv_for_user
from em2.ui.middleware import Session
from em2.ui.views.utils import View


class AddRemoveLabel(View):
    class AddRemoveQueryModel(BaseModel):
        class AddRemove(str, Enum):
            add = 'add'
            remove = 'remove'

        action: AddRemove
        label_id: int

    async def call(self):
        m = parse_request_query(self.request, self.AddRemoveQueryModel)
        if not await self.conn.fetchval(
            'select 1 from labels where id=$1 and user_id=$2', m.label_id, self.session.user_id
        ):
            raise JsonErrors.HTTPBadRequest('you do not have this label')

        conv_id, _ = await get_conv_for_user(self.conn, self.session.user_id, self.request.match_info['conv'])
        async with self.conn.transaction():
            participant_id, has_label = await self.conn.fetchrow(
                'select id, label_ids @> $1 from participants where conv=$2 and user_id=$3 for no key update',
                [m.label_id],
                conv_id,
                self.session.user_id,
            )
            if m.action == self.AddRemoveQueryModel.AddRemove.add:
                if has_label:
                    raise JsonErrors.HTTPConflict('conversation already has this label')
                await self.conn.execute(
                    'update participants set label_ids = array_append(label_ids, $1) where id=$2',
                    m.label_id,
                    participant_id,
                )
            else:
                if not has_label:
                    raise JsonErrors.HTTPConflict('conversation does not have this label')
                await self.conn.execute(
                    'update participants set label_ids = array_remove(label_ids, $1) where id=$2',
                    m.label_id,
                    participant_id,
                )
        return raw_json_response('{"status": "ok"}')


class LabelBread(Bread):
    class Model(BaseModel):
        name: constr(max_length=63)
        # TODO I guess this should be a choice so we don't have to have any inline css for csp
        color: constr(max_length=20) = None
        description: constr(max_length=1000) = None

    session = None

    browse_enabled = True
    retrieve_enabled = False
    add_enabled = True
    edit_enabled = True
    delete_enabled = True

    table = 'labels'
    browse_order_by_fields = 'ordering', 'id'
    browse_fields = 'id', 'name', 'color', 'description'

    async def handle(self):
        self.session: Session = self.request['session']
        return await super().handle()

    def where(self):
        return Where(V('user_id') == self.session.user_id)

    async def prepare_add_data(self, data):
        return {'user_id': self.session.user_id, **data}

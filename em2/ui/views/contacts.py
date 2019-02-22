from atoolbox import json_response, parse_request_query
from pydantic import BaseModel, constr

from .utils import View


class ContactSearch(View):
    class Model(BaseModel):
        query: constr(min_length=3, max_length=256, strip_whitespace=True)  # doesn't have to be an email address

    async def call(self):
        # just a bodge for now, need to use proper contact lookup
        m = parse_request_query(self.request, self.Model)

        q = m.query.lower().strip('%')
        results = await self.conn.fetch(
            """
            select distinct u.email from participants as p
            join users as u on u.id = p.user_id
            join conversations as c on c.id = p.conv
            join participants as p2 on p2.conv = c.id
            where p2.user_id=$1 and (c.publish_ts is not null or c.creator=$1) and u.email like $2
            """,
            self.session.user_id,
            f'%{q}%',
        )
        return json_response(list_=[{'name': r[0].split('@', 1)[0], 'email': r[0]} for r in results])

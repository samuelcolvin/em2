from atoolbox import raw_json_response, parse_request_query, json_response
from atoolbox import View as DefaultView
from pydantic import constr, EmailStr, BaseModel, EmailError
from pydantic.utils import validate_email
from typing import Set

from utils.db import create_missing_recipients
from utils.web import ExecView as DefaultExecView
from ..middleware import Session


class View(DefaultView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']


class ExecView(DefaultExecView):
    def __init__(self, request):
        super().__init__(request)
        self.session: Session = request['session']


class VList(View):
    sql = """
    SELECT array_to_json(array_agg(row_to_json(t)), TRUE)
    FROM (
      SELECT c.key AS key, c.subject AS subject, c.created_ts AS created_ts, c.updated_ts as updated_ts,
        c.published AS published, c.snippet as snippet
      FROM conversations AS c
      LEFT JOIN participants ON c.id = participants.conv
      WHERE participants.recipient=$1
      ORDER BY c.created_ts, c.id DESC LIMIT 50
    ) t;
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.recipient_id)
        return raw_json_response(raw_json or '[]')


class Create(ExecView):
    sql = """
    INSERT INTO conversations (key, creator, subject, published)
    VALUES                    ($1,  $2,      $3,      $4       )
    ON CONFLICT (key) DO NOTHING
    RETURNING id
    """
    add_participants_sql = 'INSERT INTO participants (conv, recipient) VALUES ($1, $2)'
    add_message_sql = 'INSERT INTO messages (conv, key, body) VALUES ($1, $2, $3)'

    class Model(BaseModel):
        subject: constr(max_length=255, strip_whitespace=True)
        message: constr(max_length=2047, strip_whitespace=True)
        participants: Set[EmailStr] = []
        publish = False

    async def execute(self, conv: Model):
        debug(conv.dict())
        conv.participants.add(self.session.address)
        recip_ids = await create_missing_recipients(self.conn, conv.participants)
        ...


class ContactSearch(View):
    class Model(BaseModel):
        query: constr(min_length=3, max_length=256)  # validation is done later

    async def call(self):
        # TODO, actually look up contacts
        m = parse_request_query(self.request, self.Model)

        options = [
            {'name': 'anne', 'address': 'anne@example.com'},
            {'name': 'ben', 'address': 'ben@example.com'},
            {'name': 'charlie', 'address': 'charlie@example.com'},
        ]
        try:
            query_name, query_address = validate_email(m.query)
        except EmailError:
            pass
        else:
            options.append({'name': query_name, 'address': query_address})
        return json_response(list_=options)

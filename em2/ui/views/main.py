from dataclasses import dataclass

from atoolbox import raw_json_response
from atoolbox import View as DefaultView

from ..middleware import Session


class View(DefaultView):
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
        debug(self.session)
        raw_json = await self.conn.fetchval(self.sql, self.session.recipient_id)
        return raw_json_response(raw_json or '[]')

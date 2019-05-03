from atoolbox import raw_json_response

from .utils import View


class GetLabels(View):
    sql = """
    select json_build_object('labels', coalesce(array_to_json(array_agg(row_to_json(t))), '[]'))
    from (
      select id, name, description, color
      from labels l
      where user_id=$1
      order by ordering, id
    ) t
    """

    async def call(self):
        raw_json = await self.conn.fetchval(self.sql, self.session.user_id)
        return raw_json_response(raw_json)

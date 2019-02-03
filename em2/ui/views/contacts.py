from atoolbox import json_response, parse_request_query
from pydantic import BaseModel, EmailError, constr
from pydantic.utils import validate_email

from .utils import View


class ContactSearch(View):
    class Model(BaseModel):
        query: constr(min_length=3, max_length=256, strip_whitespace=True)  # doesn't have to be an email address

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

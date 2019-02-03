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
            {'name': 'anne', 'email': 'anne@example.com'},
            {'name': 'ben', 'email': 'ben@example.com'},
            {'name': 'charlie', 'email': 'charlie@example.com'},
        ]
        try:
            query_name, query_email = validate_email(m.query)
        except EmailError:
            pass
        else:
            options.append({'name': query_name, 'email': query_email})
        return json_response(list_=options)

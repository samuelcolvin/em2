import base64
from email import message_from_bytes

from aiohttp import web
from aiohttp.web_response import Response


async def ses_endpoint(request):
    data = await request.post()
    raw_email = base64.b64decode(data['RawMessage.Data'])
    email = message_from_bytes(raw_email)
    d = dict(email)
    for part in email.walk():
        payload = part.get_payload(decode=True)
        if payload:
            d[f'part:{part.get_content_type()}'] = payload.decode().replace('\r\n', '\n')

    request.app['log'][-1] += ' subject="{Subject}" to="{To}"'.format(**email)
    request.app['smtp'].append(d)
    return Response(text='<MessageId>testing-msg-key</MessageId>')


routes = [web.post('/ses_endpoint/', ses_endpoint)]

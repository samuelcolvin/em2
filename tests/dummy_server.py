import base64
import json
from email import message_from_bytes

import http_ece
import nacl.encoding
import nacl.signing
from aiohttp import web
from aiohttp.hdrs import METH_GET, METH_HEAD
from aiohttp.web_response import Response
from atoolbox import json_response
from cryptography.hazmat.backends import default_backend as cryptography_default_backend
from cryptography.hazmat.primitives.asymmetric import ec


async def em2_routing(request):
    email = request.query.get('email')
    if email == 'diff@example.org':
        return json_response(node=request.headers['host'] + '/different')
    else:
        return json_response(node=request.headers['host'] + '/em2')


# b'4' * 64 from conftest settings
signing_key = nacl.signing.SigningKey(seed=b'4' * 64, encoder=nacl.encoding.HexEncoder)


async def signing_verification(request):
    return json_response(
        keys=[{'key': signing_key.verify_key.encode(encoder=nacl.encoding.HexEncoder).decode(), 'ttl': 30}]
    )


async def em2_push(request):
    request.app['em2push'].append({'body': await request.text(), 'signature': request.headers['signature']})
    return Response(status=200)


async def ses_endpoint_url(request):
    data = await request.post()
    raw_email = base64.b64decode(data['RawMessage.Data'])
    email = message_from_bytes(raw_email)
    d = dict(email)
    for part in email.walk():
        payload = part.get_payload(decode=True)
        if payload:
            d[f'part:{part.get_content_type()}'] = payload.decode().replace('\r\n', '\n')

    to_sorted = ','.join(sorted(email['To'].split(',')))
    request['log_msg'] = 'subject="{Subject}" to="{to_sorted}"'.format(to_sorted=to_sorted, **email)
    request.app['smtp'].append(d)
    return Response(text='<MessageId>testing-msg-key</MessageId>')


# any old public key, we mock verify so the key doesn't have to match the signature
public_key = (
    '-----BEGIN CERTIFICATE-----',
    'MIIFazCCBFOgAwIBAgIQDnuRfDcLJCFd0+nXpG2L3DANBgkqhkiG9w0BAQsFADBG',
    'MQswCQYDVQQGEwJVUzEPMA0GA1UEChMGQW1hem9uMRUwEwYDVQQLEwxTZXJ2ZXIg',
    'Q0EgMUIxDzANBgNVBAMTBkFtYXpvbjAeFw0xOTAyMDUwMDAwMDBaFw0yMDAxMjMx',
    'MjAwMDBaMBwxGjAYBgNVBAMTEXNucy5hbWF6b25hd3MuY29tMIIBIjANBgkqhkiG',
    '9w0BAQEFAAOCAQ8AMIIBCgKCAQEArvAsTqmW94EiC9gelZrEdR3Y2jJJwLOaRnxK',
    'oY/J/CBUEGGzfqaUBXwWnjVOImzirE57j/5ItnpW9k5kByIs7aPDuiaqaCn6Oous',
    'FqQXyem8DJp5WoFZSPhKDtLVRaOzlbMgsDIYVpcqOWfubpj7oD7/nWwICtPX7eVa',
    'jUkbaCcQExS1GY83qoL4GUpeUPN+PQ9ExNupjvi/p6lLBx2vPpcYDs2QFkT12ol6',
    'hxUCI9LRbNM/InWVP7qr9iBS3eMIP9jpr4oV7D2keztIaonLVe93psXzSh3YJm/d',
    'lnbFlIxseBrAMrUgrJE0MXcpgiCv8HrdAYfIB6XBaGA5TdXIcwIDAQABo4ICfTCC',
    'AnkwHwYDVR0jBBgwFoAUWaRmBlKge5WSPKOUByeWdFv5PdAwHQYDVR0OBBYEFH+5',
    'YRwjoZnCPO5z41lYfsedlqomMBwGA1UdEQQVMBOCEXNucy5hbWF6b25hd3MuY29t',
    'MA4GA1UdDwEB/wQEAwIFoDAdBgNVHSUEFjAUBggrBgEFBQcDAQYIKwYBBQUHAwIw',
    'OwYDVR0fBDQwMjAwoC6gLIYqaHR0cDovL2NybC5zY2ExYi5hbWF6b250cnVzdC5j',
    'b20vc2NhMWIuY3JsMCAGA1UdIAQZMBcwCwYJYIZIAYb9bAECMAgGBmeBDAECATB1',
    'BggrBgEFBQcBAQRpMGcwLQYIKwYBBQUHMAGGIWh0dHA6Ly9vY3NwLnNjYTFiLmFt',
    'YXpvbnRydXN0LmNvbTA2BggrBgEFBQcwAoYqaHR0cDovL2NydC5zY2ExYi5hbWF6',
    'b250cnVzdC5jb20vc2NhMWIuY3J0MAwGA1UdEwEB/wQCMAAwggEEBgorBgEEAdZ5',
    'AgQCBIH1BIHyAPAAdgDuS723dc5guuFCaR+r4Z5mow9+X7By2IMAxHuJeqj9ywAA',
    'AWi7Mu+5AAAEAwBHMEUCICjzfKhUDa04qWsE9ylpT3uVQR1lkQoOK3BL/jmBqm68',
    'AiEA2x/7MUblEQNBKWtWhLmFtRv2a2KPBpUvN1JCFvlx5FIAdgCHdb/nWXz4jEOZ',
    'X73zbv9WjUdWNv9KtWDBtOr/XqCDDwAAAWi7MvCPAAAEAwBHMEUCIDc9rV+Lz9Mx',
    '8rpwT38zwxyxlU81FFe6/S23FDx/UqedAiEApAItYGLRBnC0YlXe5OCF5fsL9HWy',
    'gV0fhTs6r3K09twwDQYJKoZIhvcNAQELBQADggEBAAz9vw2lMiEDgxN/jCju2gH+',
    'mkDSPyvKMBc9vPnLySBqpiu73cnvDlXWe1OXnyHXjAXWlrHlHQs5sIX6cfipUDbC',
    'siY7b2mt/uqASWMa1Qm6ROzd9J4peXYQGJEOaOBuIbDyzphlGCJc/fMwdVjU6FfH',
    'A2NL3DZnNw5r26FydzfN0HWu9B9UuvNrQ7v9XqvoBOA1QkWZpB3Hcnmu2KGNFugL',
    '5MFqgeb5yYxXORIDFATQVJRvxf43L/StvA8D3OjNiCqw057tuviFwo0WABYv1K2e',
    '9fuuyR7idsWT2+veCDK6gLdWN5hEalYIYPbgeWuhAh6CZqfPdURGbDhf2ygruhE=',
    '-----END CERTIFICATE-----',
)


async def sns_signing_endpoint(request):
    return Response(text='\n'.join(public_key))


async def s3_endpoint(request):
    # very VERY simple mock of s3
    if request.method == METH_GET:
        return Response(text=request.app['s3_files'][request.match_info['key']])
    if request.method == METH_HEAD:
        f = request.app['s3_files'].get(request.match_info['key'])
        if f:
            return Response(
                text=f, headers={'ETag': 'foobar', 'ContentDisposition': f'attachment; filename="dummy.txt"'}
            )
        else:
            return Response(text='', status=404)
    else:
        return Response(text='')


vapid_receive_key = ec.derive_private_key(1, ec.SECP256R1(), cryptography_default_backend())
# from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
# p256dh = vapid_receive_key.public_key().public_bytes(encoding=Encoding.X962, format=PublicFormat.UncompressedPoint)
# debug(base64.urlsafe_b64encode(p256dh).strip(b'=').decode())


async def vapid_endpoint(request):
    body = await request.read()
    auth = b'x' * 32
    decoded = http_ece.decrypt(
        body,
        private_key=vapid_receive_key,
        auth_secret=base64.urlsafe_b64decode(auth + b'===='[: len(auth) % 4]),
        version='aes128gcm',
    )
    data = json.loads(decoded.decode())
    request.app['webpush'].append(data)
    return Response(status=201)


async def get_image(request):
    return Response(body=b'X' * int(request.query.get('size', '10')), content_type='image/png')


routes = [
    web.get('/v1/route/', em2_routing),
    web.get('/em2/v1/signing/verification/', signing_verification),
    web.post('/em2/v1/push/{conv:[a-f0-9]{64}}/', em2_push),
    web.post('/ses_endpoint_url/', ses_endpoint_url),
    web.get('/sns_signing_url.pem', sns_signing_endpoint),
    web.route('*', '/s3_endpoint_url/{bucket}/{key:.*}', s3_endpoint),
    web.post('/vapid/', vapid_endpoint),
    web.get('/image/', get_image),
]

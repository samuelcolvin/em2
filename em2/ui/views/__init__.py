from aiohttp.web_response import Response


async def online(request):
    """
    Used by the frontend to check if it's connected to the internet. Cache-Control to cache at the CDN for 6 months.
    """
    return Response(body=b'true', content_type='text/plain', headers={'Cache-Control': 's-maxage=15552000'})

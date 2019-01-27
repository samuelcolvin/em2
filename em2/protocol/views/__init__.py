from aiohttp.web_response import Response


async def testing_view(request):
    return Response(text='this is a test')

from aiohttp import web


async def handle_index(request):
    return web.Response(
        text="Frontend is served by the src_front service.",
        content_type="text/plain",
    )

from aiohttp import web

import os

from src_core.utils.config import STATIC_DIR


async def handle_index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "assistant.html"))

from aiohttp import web
from ..utils.config import STATIC_DIR
import os

async def handle_index(request):
    return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

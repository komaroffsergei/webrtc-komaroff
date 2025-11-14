import asyncio
import os

from aiohttp import web
import logging

from ..utils.download_models import is_model_exists, download_model_async
from ..utils.sse import sse_log, make_async_callback

logger = logging.getLogger("handle_startup")

async def handle_startup(app: web.Application):
    logger.info("startup")
    loop = asyncio.get_running_loop()

    def on_status(msg: str):
        # msg может быть "downloading", "progress|12", "downloaded", "error"
        loop.call_soon_threadsafe(
            asyncio.create_task,
            app["methods"]["sse_broadcast"](
                {"type": "model_status", "value": msg},
            ),
        )

    download_model_async(
        model_url=app["data"]["WHISPER_MODEL_URL"],
        models_dir=str(app["data"]["WHISPER_MODEL_DIR"]),
        sha256=app["data"]["WHISPER_MODEL_SHA256"],
        on_status=on_status,
    )



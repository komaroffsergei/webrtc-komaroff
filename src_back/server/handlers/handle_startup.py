import asyncio
import json
import logging
import os
from aiohttp import web

from ..utils.sse import sse_log
from ..utils.nats_client import NatsClient
from ..utils.download_models import download_model_async

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):
    logger.info("Startup sequence begin")
    loop = asyncio.get_running_loop()

    #
    # NATS
    #
    nats_client = NatsClient(app['vars']['NATS_URL'])
    await nats_client.connect()
    app['services'] = {
        'nats_client': nats_client
    }
    async def _log_cb(msg):
        try:
            data = json.loads(msg.data.decode())
            await sse_log(
                app,
                data.get("message", ""),
                level=data.get("type", "info"),
                service=data.get("service", "whisper"),
                log_time=data.get("time"),
            )
        except Exception as e:
            logger.warning("Error parsing whisper log: %s", e)

    await app['services']['nats_client'].subscribe(app['vars']['NATS_LOGS_SUBJECT'], _log_cb)
    # loop.call_soon_threadsafe(
    #     asyncio.create_task,
    #     app["methods"]["sse_broadcast"]('asdasd')
    # )
    # await sse_log(app, f"Subscribed to logs: `{app['vars']['NATS_LOGS_SUBJECT']}`")

    #
    # MODEL DOWNLOAD
    #
    # def on_status_update(status):
    #     loop.call_soon_threadsafe(
    #         asyncio.create_task,
    #         app["methods"]["sse_broadcast"](status)
    #     )

    # download_model_async(
    #     model_url=app["data"]["WHISPER_MODEL_URL"],
    #     models_dir=str(app["data"]["WHISPER_MODEL_DIR"]),
    #     sha256=app["data"]["WHISPER_MODEL_SHA256"],
    #     on_status=on_status_update,
    # )

    # await sse_log(app, "Model download started")
    logger.info("Startup complete")

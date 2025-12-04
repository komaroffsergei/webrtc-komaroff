import json
import logging
import os
from pathlib import Path
from aiohttp import web

from ..settings import NATS_LOGS_SUBJECT, NATS_URL, STACK_SERVICE_NAME, VAD_MODEL_URL
from ..utils.nats_client import NatsClient
from ..utils.silero_downloader import ensure_silero_model
from ..utils.sse import sse_log

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):

    # NATS
    nats_client = NatsClient(NATS_URL)
    await nats_client.connect()
    app['services'] = {
        'nats_client': nats_client
    }
    async def _log_cb(msg):
        try:
            data = json.loads(msg.data.decode())
            await sse_log(
                data.get("message", ""),
                level=data.get("type", "info"),
                name=data.get("name"),
            )
        except Exception as e:
            logger.warning("Error parsing whisper log: %s", e)

    await app['services']['nats_client'].subscribe(NATS_LOGS_SUBJECT, _log_cb)
    await ensure_silero_model(
        app,
        url=VAD_MODEL_URL,
        service=STACK_SERVICE_NAME,
    )

    logger.info("Startup complete")

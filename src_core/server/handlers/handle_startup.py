import json
import logging
import os
from pathlib import Path
from aiohttp import web

from shared.sse import sse_log
from ..utils.nats_client import NatsClient
from ..utils.silero_downloader import ensure_silero_model
from ..utils.sse import get_sse_context
from ...main import NATS_URL, NATS_LOGS_SUBJECT, STACK_SERVICE_NAME, VAD_MODEL_URL

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):

    ctx = get_sse_context(app)


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
                ctx,
                data.get("message", ""),
                level=data.get("type", "info"),
                service=data.get("service", "whisper"),
                log_time=data.get("time"),
                name=data.get("name"),
            )
        except Exception as e:
            logger.warning("Error parsing whisper log: %s", e)

    await app['services']['nats_client'].subscribe(NATS_LOGS_SUBJECT, _log_cb)
    await ensure_silero_model(
        ctx,
        url=VAD_MODEL_URL,
        service=STACK_SERVICE_NAME,
    )

    logger.info("Startup complete")



import json
import logging
from aiohttp import web

from src_core.settings import NATS_URL, STACK_SERVICE_NAME, VAD_MODEL_URL
from src_core.utils.nats_client import NatsClient
from src_core.utils.silero_downloader import ensure_silero_model
from src_core.utils.sse import sse_log

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

    await app['services']['nats_client'].subscribe(app['vars']['NATS_EVENTS_SUBJECT'], _log_cb)
    await ensure_silero_model(
        app,
        url=VAD_MODEL_URL,
        service=STACK_SERVICE_NAME,
    )

    logger.info("Startup complete")

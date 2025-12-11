import logging
from aiohttp import web

from src_core.settings import NATS_URL, STACK_SERVICE_NAME, VAD_MODEL_URL
from src_core.utils.nats_client import NatsClient
from src_core.utils.silero_downloader import ensure_silero_model
from src_core.utils.event_bus import register_event_bus, event_log

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):

    # NATS
    nats_client = NatsClient(NATS_URL)
    await nats_client.connect()
    app['services'] = {
        'nats_client': nats_client
    }

    register_event_bus(
        app,
        nats_client=nats_client,
        subject=app['vars']['NATS_EVENTS_SUBJECT'],
        service_name=STACK_SERVICE_NAME,
    )

    await event_log("Core service started", level="info", app=app)
    await ensure_silero_model(
        app,
        url=VAD_MODEL_URL,
        service=STACK_SERVICE_NAME,
    )

    logger.info("Startup complete")

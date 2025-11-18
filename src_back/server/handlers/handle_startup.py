import asyncio
import json
import logging
import os
from aiohttp import web

from ..utils.sse import sse_log
from ..utils.nats_client import NatsClient

logger = logging.getLogger("startup")


async def handle_startup(app: web.Application):
    # NATS
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
                name=data.get("name"),
            )
        except Exception as e:
            logger.warning("Error parsing whisper log: %s", e)

    await app['services']['nats_client'].subscribe(app['vars']['NATS_LOGS_SUBJECT'], _log_cb)

    logger.info("Startup complete")

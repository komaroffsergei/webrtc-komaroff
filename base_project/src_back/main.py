import asyncio
import contextlib
import logging
from aiohttp import web
import os

from server.handlers.handle_index import handle_index
from server.handlers.handle_message import message_handler
from server.handlers.handle_offer import handle_offer
from server.handlers.handle_shutdown import handle_shutdown
from server.handlers.handle_startup import handle_startup
from server.utils.config import STATIC_DIR
from server.utils.sse import sse_handler, sse_broadcast

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_back")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_FRAMES_SUBJECT = os.getenv("NATS_FRAMES_SUBJECT", "nats.frames")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")

def setup_routes(app):
    app.router.add_get("/", handle_index)
    app.router.add_post("/offer", handle_offer)
    app.router.add_post("/message", message_handler)
    app.router.add_static("/static", path=STATIC_DIR)
    app.router.add_get("/events", sse_handler)
    app.on_startup.append(handle_startup)
    app.on_shutdown.append(handle_shutdown)

if __name__ == "__main__":
    app = web.Application(client_max_size=1_048_576)
    app["pcs"] = set()
    app["sse_clients"] = set()
    app["methods"] = {
        "sse_broadcast": lambda msg: sse_broadcast(app, msg)
    }
    app['vars'] = {
        "NATS_FRAMES_SUBJECT": NATS_FRAMES_SUBJECT,
        "NATS_LOGS_SUBJECT": NATS_LOGS_SUBJECT,
        "NATS_URL": NATS_URL,
        "STACK_SERVICE_NAME": STACK_SERVICE_NAME,
    }

    setup_routes(app)
    logger = logging.getLogger(__name__)
    logger.info("http://localhost:8000")
    port = int(os.getenv("PORT", "8000"))

    async def ticker(app):
        counter = 0
        try:
            while True:
                counter += 1
                await sse_broadcast(
                    app,
                    {
                        "service": STACK_SERVICE_NAME,
                        "type": "debug",
                        "name": "heartbeat",
                        "message": f"heartbeat #{counter}",
                    },
                    ensure_meta=False,
                )
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def on_startup(app):
        app["ticker_task"] = asyncio.create_task(ticker(app))

    async def on_cleanup(app):
        task = app.get("ticker_task")
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)

    web.run_app(app, host="0.0.0.0", port=port)

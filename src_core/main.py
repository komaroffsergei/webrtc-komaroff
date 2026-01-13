import asyncio
import logging
import sys
from pathlib import Path

from aiohttp import web

from src_core.handlers.handle_message import message_handler

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src_core.handlers.handle_index import handle_index

from src_core.handlers.handle_offer import handle_offer
from src_core.handlers.handle_shutdown import handle_shutdown
from src_core.handlers.handle_startup import handle_startup

from src_core.settings import (
    CORE_HOST,
    CORE_PORT,
    STACK_SERVICE_NAME,
    NATS_URL,
    USER_ID,
    NATS_EVENTS_SUBJECT,
    NATS_AGENT_SUBJECT,
    NATS_ASR_SUBJECT,
)

logger = logging.getLogger(STACK_SERVICE_NAME)


def setup_routes(app):
    app.router.add_get("/core", handle_index)
    app.router.add_post("/core/offer", handle_offer)
    app.router.add_post("/core/message", message_handler)

    app.on_startup.append(handle_startup)
    app.on_shutdown.append(handle_shutdown)


if __name__ == "__main__":
    app = web.Application(client_max_size=1_048_576)
    app["pcs"] = set()
    app['vars'] = {
        "NATS_URL": NATS_URL,
        "STACK_SERVICE_NAME": STACK_SERVICE_NAME,
        "NATS_EVENTS_SUBJECT": f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        "NATS_AGENT_SUBJECT": f"{NATS_AGENT_SUBJECT}{USER_ID}",
        "NATS_ASR_SUBJECT": f"{NATS_ASR_SUBJECT}{USER_ID}",
        "USER_ID": USER_ID
    }
    setup_routes(app)


    # async def on_startup(app):
    #     app["ticker_task"] = asyncio.create_task(ticker(app))
    #
    # async def on_cleanup(app):
    #     task = app.get("ticker_task")
    #     if task:
    #         task.cancel()
    #         with contextlib.suppress(asyncio.CancelledError):
    #             await task

    # app.on_startup.append(on_startup)
    # app.on_cleanup.append(on_cleanup)

    web.run_app(app, host=CORE_HOST, port=CORE_PORT)

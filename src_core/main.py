import asyncio
import contextlib
import logging
from aiohttp import web
import os
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server.handlers.handle_index import handle_index
from server.handlers.handle_message import message_handler
from server.handlers.handle_offer import handle_offer
from server.handlers.handle_shutdown import handle_shutdown
from server.handlers.handle_startup import handle_startup
from server.utils.config import STATIC_DIR
from src_core.server.handlers.handle_sse import sse_handler, sse_broadcast

STACK_SERVICE_NAME = os.getenv("STACK_SERVICE_NAME", "src_core")
CORE_PORT=os.getenv("CORE_PORT", 8000)
CORE_HOST=os.getenv("CORE_HOST", "0.0.0.0")
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
ASR_MODELS_DIR = os.getenv("ASR_MODELS_DIR", "/app/models/asr")
ASR_MODEL_ID = os.getenv("ASR_MODEL_ID", "Systran/faster-whisper-small")
NATS_FRAMES_SUBJECT = os.getenv("NATS_FRAMES_SUBJECT", "nats.frames")
NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
VAD_MODEL_PATH = os.getenv("VAD_MODEL_PATH", "models/vad")
VAD_MODEL_URL = os.getenv("VAD_MODEL_URL", "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx")

logger = logging.getLogger(STACK_SERVICE_NAME)

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
                await asyncio.sleep(5)
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

    web.run_app(app, host=CORE_HOST, port=CORE_PORT)

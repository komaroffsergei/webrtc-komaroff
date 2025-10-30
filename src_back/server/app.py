import logging
from aiohttp import web

from .handlers.handle_index import handle_index
from .handlers.handle_offer import handle_offer
from .handlers.handle_shutdown import handle_shutdown
from .handlers.sse import sse_handler
from .utils.config import STATIC_DIR


def setup_routes(app):
    app.router.add_get("/", handle_index)
    app.router.add_post("/offer", handle_offer)
    app.router.add_static("/static", path=STATIC_DIR)
    app.router.add_get("/events", sse_handler)
    logger = logging.getLogger(__name__)
    logger.info("http://localhost:8000")


def create_app():
    app = web.Application(client_max_size=1_048_576)
    app["pcs"] = set()
    app["sse_clients"] = set()
    setup_routes(app)
    app.on_shutdown.append(handle_shutdown)
    return app
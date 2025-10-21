import logging
from aiohttp import web

from .handlers.handle_index import handle_index
from .handlers.handle_offer import handle_offer
from .handlers.handle_shutdown import handle_shutdown
from .libs.call_manager import CallManager
from .utils.config import STATIC_DIR


def setup_routes(app):
    app.router.add_get("/", handle_index)
    app.router.add_post("/offer", handle_offer)
    app.router.add_static("/static", path=STATIC_DIR)
    logger = logging.getLogger(__name__)
    logger.info("http://localhost:8000")


def create_app():
    app = web.Application(client_max_size=1_048_576)
    app["pcs"] = set()
    # app["call_manager"] = CallManager(app)
    setup_routes(app)
    app.on_shutdown.append(handle_shutdown)
    return app
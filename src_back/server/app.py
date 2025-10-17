import os

from aiohttp import web

from .handler import handle_index, handle_offer, handle_shutdown
from .utils.config import STATIC_DIR


def setup_routes(app):
    app.router.add_get("/", handle_index)
    app.router.add_post("/offer", handle_offer)
    # Trickle ICE endpoints (REST fallback)
    from .handler import handle_trickle_post, handle_trickle_get, handle_ws
    app.router.add_post("/trickle", handle_trickle_post)
    app.router.add_get("/trickle", handle_trickle_get)
    # WebSocket for full-duplex trickle
    app.router.add_get("/ws", handle_ws)
    app.router.add_static("/static", path=STATIC_DIR)

    import logging
    logger = logging.getLogger(__name__)
    logger.info("http://localhost:8080")

def create_app():
    app = web.Application(client_max_size=1_048_576)
    app["pcs"] = set()
    setup_routes(app)

    app.on_shutdown.extend([handle_shutdown])

    return app

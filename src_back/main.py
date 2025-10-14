import logging
from aiohttp import web

from server.app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    app = create_app()
    web.run_app(app, host="0.0.0.0", port=8080)

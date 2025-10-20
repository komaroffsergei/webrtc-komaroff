from aiohttp import web

from server.app import create_app

if __name__ == "__main__":
    app = create_app()
    import os
    port = int(os.getenv("PORT", "8000"))
    web.run_app(app, host="0.0.0.0", port=port)

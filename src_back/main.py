import logging
from aiohttp import web

# Ensure aiortc boot patch applied before any RTCPeerConnection is constructed
import os
os.environ.setdefault("AIORTC_ICE_GATHERING_TIMEOUT_MS", "300")
from server import boot_patch  # noqa: F401  # side-effect import
from server.app import create_app

if __name__ == "__main__":
    # Console logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # Dedicated file logging for WebRTC offer timings
    webrtc_logger = logging.getLogger("webrtc")
    webrtc_logger.setLevel(logging.INFO)
    try:
        fh = logging.FileHandler("offer_timing.log", mode="a", encoding="utf-8")
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        # Avoid duplicate handlers on reloads
        if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) and str(h.baseFilename).endswith("offer_timing.log") for h in webrtc_logger.handlers):
            webrtc_logger.addHandler(fh)
    except Exception:
        # Fall back silently to console-only if file cannot be opened
        pass

    app = create_app()
    import os
    port = int(os.getenv("PORT", "8000"))
    web.run_app(app, host="0.0.0.0", port=port)

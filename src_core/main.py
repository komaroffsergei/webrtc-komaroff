import logging
import os
import sys
import socket
from pathlib import Path

from aiohttp import web

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# --- OTel ---
from otel import OTelBootstrap

# --- src_core imports ---
from src_core.handlers.handle_index import handle_index
from src_core.handlers.handle_offer import handle_offer
from src_core.handlers.handle_message import message_handler
from src_core.handlers.handle_init_map import init_map_handler
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
    ASR_IN_PREFIX,
    ASR_OUT_PREFIX,
    OTEL_EXPORTER_OTLP_ENDPOINT,
    OTEL_EXPORTER_OTLP_ENDPOINT_FRONT,
    OTEL_LOG_LEVEL,
    OTEL_RESOURCE_ATTRIBUTES, OTEL_TRACES_EXPORTER, OTEL_METRICS_EXPORTER,
)

logger = logging.getLogger(STACK_SERVICE_NAME)


def setup_routes(app: web.Application) -> None:
    app.router.add_get("/core", handle_index)
    app.router.add_post("/core/offer", handle_offer)
    app.router.add_post("/core/message", message_handler)
    app.router.add_post("/core/init_map", init_map_handler)

    app.on_startup.append(handle_startup)
    app.on_shutdown.append(handle_shutdown)

def _ensure_bindable(host: str, port: int) -> None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
    except OSError as exc:
        if exc.errno == 98:
            raise RuntimeError(
                f"Cannot bind to {host}:{port} (address already in use). "
                "If docker-compose is running, stop the src_core container or set CORE_PORT to a free port."
            ) from None
        raise
    finally:
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    app = web.Application(client_max_size=1_048_576)

    app["pcs"] = set()
    app["vars"] = {
        "NATS_URL": NATS_URL,
        "STACK_SERVICE_NAME": STACK_SERVICE_NAME,
        "NATS_EVENTS_SUBJECT": f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        "NATS_AGENT_SUBJECT": f"{NATS_AGENT_SUBJECT}{USER_ID}",
        "ASR_IN_PREFIX": ASR_IN_PREFIX,
        "ASR_OUT_PREFIX": ASR_OUT_PREFIX,
        "USER_ID": USER_ID,
    }

    # --- OTel bootstrap ---
    otelb = OTelBootstrap.from_env(
        service_name=STACK_SERVICE_NAME,
        OTEL_EXPORTER_OTLP_ENDPOINT=OTEL_EXPORTER_OTLP_ENDPOINT,
        OTEL_EXPORTER_OTLP_ENDPOINT_FRONT=OTEL_EXPORTER_OTLP_ENDPOINT_FRONT,
        OTEL_LOG_LEVEL=OTEL_LOG_LEVEL,
        OTEL_METRICS_EXPORTER=OTEL_METRICS_EXPORTER,
        OTEL_RESOURCE_ATTRIBUTES=OTEL_RESOURCE_ATTRIBUTES,
        OTEL_TRACES_EXPORTER=OTEL_TRACES_EXPORTER,
    )

    otelb.instrument_aiohttp_app(app)
    app["otel"] = otelb

    app["otel"] = otelb

    setup_routes(app)

    try:
        _ensure_bindable(CORE_HOST, CORE_PORT)
        web.run_app(app, host=CORE_HOST, port=CORE_PORT)
    except Exception as exc:
        logger.error("%s", str(exc))
        raise SystemExit(1)

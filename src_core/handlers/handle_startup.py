import logging
from aiohttp import web

from otel import OTelBootstrap
from src_core.settings import NATS_URL, STACK_SERVICE_NAME
from src_core.utils.nats_client import NatsClient
from src_core.utils.event_bus import register_event_bus, event_log

logger = logging.getLogger("startup")


@OTelBootstrap.span(
    "nats.connect",
    attributes={"nats.url": (NATS_URL or "").split("@")[-1]},
)
async def _nats_connect(app: web.Application) -> NatsClient:
    nats_client = NatsClient(NATS_URL)
    await nats_client.connect()
    app["services"] = {"nats_client": nats_client}
    return nats_client


@OTelBootstrap.span(
    "event_bus.register",
    attributes_from_args=lambda app, nats_client: {
        "messaging.system": "nats",
        "messaging.destination": app["vars"].get("NATS_EVENTS_SUBJECT", ""),
        "messaging.destination_kind": "topic",
    },
)
def _event_bus_register(app: web.Application, *, nats_client: NatsClient) -> None:
    subject = app["vars"].get("NATS_EVENTS_SUBJECT", "")
    register_event_bus(
        app,
        nats_client=nats_client,
        subject=subject,
        service_name=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "event_log.started",
    attributes={"event.type": "log", "event.level": "info"},
)
async def _event_log_started(app: web.Application) -> None:
    await event_log(
        "log",
        "info",
        {"text": "Core service started"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "event_log.startup_failed",
    attributes_from_args=lambda app, exc: {
        "event.type": "log",
        "event.level": "error",
        "error.message": str(exc),
    },
)
async def _event_log_startup_failed(app: web.Application, exc: Exception) -> None:
    await event_log(
        "log",
        "error",
        {"text": f"Core startup failed: {exc}"},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "app.startup",
    attributes={
        "service.name": STACK_SERVICE_NAME,
        "nats.url.set": bool(NATS_URL),
    },
    ok_attributes={"startup.ok": True},
)
async def handle_startup(app: web.Application):
    try:
        nats_client = await _nats_connect(app)
        _event_bus_register(app, nats_client=nats_client)
        await _event_log_started(app)

        logger.info("Startup complete")

    except Exception as exc:
        logger.exception("Startup failed")

        # Best-effort attempt to log the failure via the event bus.
        try:
            await _event_log_startup_failed(app, exc)
        except Exception:
            # Do not mask the original error.
            pass

        raise

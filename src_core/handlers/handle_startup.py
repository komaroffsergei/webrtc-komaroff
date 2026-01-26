import logging
from aiohttp import web

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from src_core.settings import NATS_URL, STACK_SERVICE_NAME, VAD_MODEL_URL
from src_core.utils.nats_client import NatsClient
from src_core.utils.silero_downloader import ensure_silero_model
from src_core.utils.event_bus import register_event_bus, event_log

logger = logging.getLogger("startup")
tracer = trace.get_tracer(__name__)


async def handle_startup(app: web.Application):
    with tracer.start_as_current_span("app.startup") as span:
        span.set_attribute("service.name", STACK_SERVICE_NAME)
        span.set_attribute("nats.url.set", bool(NATS_URL))
        span.set_attribute("vad.model_url.set", bool(VAD_MODEL_URL))

        try:
            # --- NATS connect
            with tracer.start_as_current_span("nats.connect") as sp:
                # не логируем полный URL, если там вдруг креды
                sp.set_attribute("nats.url", (NATS_URL or "").split("@")[-1])

                nats_client = NatsClient(NATS_URL)
                await nats_client.connect()

                app["services"] = {
                    "nats_client": nats_client
                }

            # --- Event bus registration
            with tracer.start_as_current_span("event_bus.register") as sp:
                subject = app["vars"].get("NATS_EVENTS_SUBJECT", "")
                sp.set_attribute("messaging.system", "nats")
                sp.set_attribute("messaging.destination", subject)
                sp.set_attribute("messaging.destination_kind", "topic")

                register_event_bus(
                    app,
                    nats_client=nats_client,
                    subject=subject,
                    service_name=STACK_SERVICE_NAME,
                )

            # --- Startup event log
            with tracer.start_as_current_span("event_log.started") as sp:
                sp.set_attribute("event.type", "log")
                sp.set_attribute("event.level", "info")
                await event_log(
                    "log",
                    "info",
                    {"text": "Core service started"},
                    app=app,
                    service=STACK_SERVICE_NAME,
                )

            # --- Ensure Silero VAD model
            with tracer.start_as_current_span("vad.ensure_model") as sp:
                sp.set_attribute("model.url", VAD_MODEL_URL)
                await ensure_silero_model(app, url=VAD_MODEL_URL)

            logger.info("Startup complete")
            span.set_attribute("startup.ok", True)

        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            logger.exception("Startup failed")

            # Попробуем залогировать ошибку в event bus (best effort)
            try:
                with tracer.start_as_current_span("event_log.startup_failed") as sp:
                    sp.set_attribute("event.type", "log")
                    sp.set_attribute("event.level", "error")
                    sp.set_attribute("error.message", str(e))
                    await event_log(
                        "log",
                        "error",
                        {"text": f"Core startup failed: {e}"},
                        app=app,
                        service=STACK_SERVICE_NAME,
                    )
            except Exception:
                # не маскируем исходную ошибку
                pass

            raise

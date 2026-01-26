import asyncio
from aiohttp import web

from opentelemetry import trace
from opentelemetry.trace import StatusCode

tracer = trace.get_tracer(__name__)


async def handle_shutdown(app: web.Application):
    with tracer.start_as_current_span("app.shutdown") as span:
        try:
            pcs = list(app.get("pcs", []))
            span.set_attribute("webrtc.pcs.count", len(pcs))

            # --- Close peer connections
            with tracer.start_as_current_span("webrtc.pcs.close_all") as sp:
                results = await asyncio.gather(*(pc.close() for pc in pcs), return_exceptions=True)

                # посчитаем, сколько реально упало при закрытии
                errors = [r for r in results if isinstance(r, Exception)]
                sp.set_attribute("webrtc.pcs.close.errors", len(errors))

                if errors:
                    # записывать все исключения подряд может быть шумно,
                    # поэтому пишем первое, остальное считается метрикой выше
                    sp.record_exception(errors[0])
                    sp.set_status(StatusCode.ERROR)

            # --- Clear pcs set
            with tracer.start_as_current_span("webrtc.pcs.clear"):
                if "pcs" in app:
                    app["pcs"].clear()

            # --- Shutdown OTel (best-effort)
            otel_obj = app.get("otel")
            with tracer.start_as_current_span("otel.shutdown") as sp:
                sp.set_attribute("otel.present", otel_obj is not None)
                if otel_obj is not None:
                    otel_obj.shutdown()

            span.set_attribute("shutdown.ok", True)

        except Exception as e:
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            raise

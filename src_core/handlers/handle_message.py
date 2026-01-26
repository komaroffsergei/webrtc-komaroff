import logging
from aiohttp import web

from opentelemetry import trace
from opentelemetry.trace import StatusCode

from src_core.handlers.handle_transcription import handle_transcription
from src_core.settings import STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_message")
tracer = trace.get_tracer(__name__)


async def message_handler(request: web.Request):
    with tracer.start_as_current_span("core.message") as span:
        span.set_attribute("http.route", "/core/message")
        span.set_attribute("service.name", STACK_SERVICE_NAME)

        try:
            # --- Parse JSON
            with tracer.start_as_current_span("message.parse_json") as sp:
                try:
                    data = await request.json()
                except Exception as e:
                    sp.record_exception(e)
                    sp.set_status(StatusCode.ERROR)
                    logger.exception("Invalid JSON")
                    span.set_status(StatusCode.ERROR)
                    return web.json_response({"error": "Invalid JSON"}, status=400)

            # --- Validate payload
            with tracer.start_as_current_span("message.validate") as sp:
                text = data.get("text", "")
                text = text.strip() if isinstance(text, str) else ""

                sp.set_attribute("message.text.length", len(text))

                if not text:
                    sp.set_status(StatusCode.ERROR)
                    span.set_status(StatusCode.ERROR)
                    return web.json_response(
                        {"error": "text field is required"},
                        status=400,
                    )

                session_id = data.get("session_id")
                edit = data.get("edit")

                sp.set_attribute("message.session_id.present", bool(session_id))
                sp.set_attribute("message.edit.present", bool(edit))

            # --- Event log (can block / fail, so separate span)
            with tracer.start_as_current_span("event_log.message") as sp:
                sp.set_attribute("event.type", "log")
                sp.set_attribute("event.level", "info")
                await event_log(
                    "log",
                    "info",
                    {"text": text},
                    app=request.app,
                    service=STACK_SERVICE_NAME,
                )

            # --- Build payload for transcription
            payload = {"text": text}
            if session_id:
                payload["session_id"] = session_id
            if edit:
                payload["edit"] = edit

            # --- Transcription handler
            with tracer.start_as_current_span("transcription.handle") as sp:
                sp.set_attribute("transcription.session_id.present", bool(session_id))
                response = await handle_transcription(request.app, payload)

            # --- Build response
            session_id_out = (
                response.get("session_id")
                if isinstance(response, dict)
                else None
            )
            span.set_attribute("response.session_id.present", bool(session_id_out))
            span.set_attribute("message.ok", True)

            return web.json_response(
                {"status": "ok", "session_id": session_id_out},
            )

        except Exception as e:
            # Любой неожиданный косяк
            span.record_exception(e)
            span.set_status(StatusCode.ERROR)
            logger.exception("Unhandled error in message_handler")
            return web.json_response(
                {"error": "internal error"},
                status=500,
            )

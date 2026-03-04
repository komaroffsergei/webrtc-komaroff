import logging
import json
from aiohttp import web

from opentelemetry.trace import StatusCode

from otel import OTelBootstrap
from src_core.handlers.handle_transcription import handle_transcription
from src_core.settings import STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_message")


def _first_error_message(errors: object) -> str | None:
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0]
    if not isinstance(first, dict):
        return None
    msg = first.get("message")
    if isinstance(msg, str) and msg.strip():
        return msg.strip()
    code = first.get("code")
    if isinstance(code, str) and code.strip():
        return code.strip()
    return None


def _attrs_from_aiohttp_json_response(resp: web.StreamResponse):
    attrs = {"message.ok": getattr(resp, "status", 200) < 400}
    body = getattr(resp, "body", None)
    if not body:
        return attrs
    try:
        data = json.loads(body.decode("utf-8"))
    except Exception:
        return attrs
    attrs["response.session_id.present"] = bool(data.get("session_id")) if isinstance(data, dict) else False
    return attrs


@OTelBootstrap.span("message.parse_json")
async def _parse_json(request: web.Request):
    return await request.json()


@OTelBootstrap.span(
    "message.validate",
    attributes_from_result=lambda r: {
        "message.text.length": len(r[1]),
        "message.session_id.present": bool(r[2]),
        "message.turn_id.present": bool(r[3]),
        "message.edit.present": bool(r[4]),
    },
    status_from_result=lambda r: StatusCode.ERROR if not r[0] else None,
)
def _validate_payload(data):
    text = data.get("text", "")
    text = text.strip() if isinstance(text, str) else ""

    session_id = data.get("session_id")
    turn_id = data.get("turn_id")
    edit = data.get("edit")
    ok = bool(text)
    return ok, text, session_id, turn_id, edit


@OTelBootstrap.span(
    "event_log.message",
    attributes={"event.type": "log", "event.level": "info"},
)
async def _event_log_message(app: web.Application, text: str) -> None:
    await event_log(
        "log",
        "info",
        {"text": text},
        app=app,
        service=STACK_SERVICE_NAME,
    )


@OTelBootstrap.span(
    "transcription.handle",
    attributes_from_args=lambda app, payload, has_session_id: {"transcription.session_id.present": bool(has_session_id)},
)
async def _transcription_handle(app: web.Application, payload, *, has_session_id: bool):
    return await handle_transcription(app, payload)


@OTelBootstrap.span(
    "core.message",
    attributes={"http.route": "/core/message", "service.name": STACK_SERVICE_NAME},
    attributes_from_result=_attrs_from_aiohttp_json_response,
    ignored_exceptions=(web.HTTPBadRequest,),
)
async def message_handler(request: web.Request):
    try:
        try:
            data = await _parse_json(request)
        except Exception as exc:
            logger.exception("Invalid JSON")
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "Invalid JSON"}),
                content_type="application/json",
            ) from exc

        ok, text, session_id, turn_id, edit = _validate_payload(data)
        if not ok:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "text field is required"}),
                content_type="application/json",
            )

        await _event_log_message(request.app, text)

        payload = {"text": text}
        if session_id:
            payload["session_id"] = session_id
        if turn_id:
            payload["turn_id"] = turn_id
        if edit:
            payload["edit"] = edit

        response = await _transcription_handle(request.app, payload, has_session_id=bool(session_id))

        if not isinstance(response, dict):
            raise web.HTTPBadGateway(
                text=json.dumps({"error": "invalid_agent_response"}),
                content_type="application/json",
            )

        session_id_out = response.get("session_id")
        if response.get("error"):
            details = response.get("details")
            error_code = response.get("error")
            body = {
                "status": "error",
                "session_id": session_id_out,
                "error": error_code,
                "details": details if isinstance(details, str) and details.strip() else None,
            }
            status_code = 504 if error_code == "agent_communication" else 502
            return web.json_response(body, status=status_code)

        status = str(response.get("status") or "").strip().upper()
        if response.get("ok") is False or status == "FAILED":
            error_message = _first_error_message(response.get("errors")) or "Agent request failed."
            body = {
                "status": "error",
                "session_id": session_id_out,
                "error": error_message,
            }
            return web.json_response(body, status=502)

        return web.json_response({"status": "ok", "session_id": session_id_out})

    except web.HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unhandled error in message_handler")
        raise web.HTTPInternalServerError(
            text=json.dumps({"error": "internal error"}),
            content_type="application/json",
        ) from exc

import json
import logging
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src_core.settings import STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log
from src_shared.contracts.common import now_ts_ms

logger = logging.getLogger("handle_transcription")


def _normalize_turn_id(raw_turn_id: object, raw_phrase_id: object) -> str:
    for value in (raw_turn_id, raw_phrase_id):
        if not isinstance(value, str):
            continue
        candidate = value.strip()
        if not candidate:
            continue
        try:
            return str(UUID(candidate))
        except Exception:
            # Keep deterministic mapping for non-UUID phrase identifiers from ASR stream.
            return str(uuid5(NAMESPACE_URL, candidate))
    return str(uuid4())


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    out = value.strip()
    return out or None


async def handle_transcription(app, payload: dict):
    """Handle transcriptions and forward requests to the agent via NATS."""
    text = (payload.get("text") or "").strip()
    session_id = _clean_text(payload.get("session_id"))
    phrase_id = _clean_text(payload.get("phrase_id"))
    raw_turn_id = payload.get("turn_id")

    if not text:
        if payload.get("pending") is True:
            data = {"pending": True}
            if phrase_id:
                data["phrase_id"] = phrase_id
            if session_id:
                data["session_id"] = session_id
            if raw_turn_id or phrase_id:
                data["turn_id"] = _normalize_turn_id(raw_turn_id, phrase_id)
            await event_log(
                "command",
                "transcription_pending",
                data,
                app=app,
                service=STACK_SERVICE_NAME,
            )
            return {"status": "pending"}

        logger.warning("Empty transcription payload")
        return {}

    logger.info("handle_transcription: '%s'", text)

    turn_id = _normalize_turn_id(raw_turn_id, phrase_id)
    if phrase_id:
        await event_log(
            "command",
            "transcription",
            {"text": text, "phrase_id": phrase_id, "turn_id": turn_id},
            app=app,
            service=STACK_SERVICE_NAME,
        )
    await event_log(
        "command",
        "voice",
        {"blocked": True},
        app=app,
        service=STACK_SERVICE_NAME,
    )

    try:
        nc = app['services']['nats_client']
        edit = payload.get("edit")
        trace_id = uuid4()
        msg = await nc.request(
            app['vars']['NATS_AGENT_SUBJECT'],
            json.dumps({
                "trace_id": str(trace_id),
                "request_id": str(uuid4()),
                "correlation_id": str(trace_id),
                "ts_ms": now_ts_ms(),
                "text": text,
                "session_id": session_id,
                "turn_id": turn_id,
                "edit": edit,
                "user_id": app["vars"].get("USER_ID"),
            }, ensure_ascii=False).encode("utf-8"),
            timeout=NATS_REQUEST_TIMEOUT,
        )

        response = json.loads(msg.data.decode("utf-8"))
        return response

    except Exception as e:
        await event_log(
            "log",
            "error",
            {"text": f"Agent communication error: {str(e)}"},
            app=app,
            service=STACK_SERVICE_NAME,
        )
        return {"error": "agent_communication", "details": str(e)}
    finally:
        try:
            await event_log(
                "command",
                "voice",
                {"blocked": False},
                app=app,
                service=STACK_SERVICE_NAME,
            )
        except Exception:
            logger.exception("Failed to publish voice unblock event")

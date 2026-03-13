import json
import logging
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src_core.settings import STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log
from src_shared.contracts.common import now_ts_ms

logger = logging.getLogger("handle_transcription")


def _clean_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


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
            return str(uuid5(NAMESPACE_URL, candidate))
    return str(uuid4())


async def _publish_voice_block(app, blocked: bool) -> None:
    await event_log(
        "command",
        "voice",
        {"blocked": blocked},
        app=app,
        service=STACK_SERVICE_NAME,
    )


async def _request_agent(
    app,
    *,
    text: str,
    session_id: str | None,
    turn_id: str,
    edit: object = None,
) -> dict:
    nc = app["services"]["nats_client"]
    trace_id = uuid4()
    msg = await nc.request(
        app["vars"]["NATS_AGENT_SUBJECT"],
        json.dumps(
            {
                "trace_id": str(trace_id),
                "request_id": str(uuid4()),
                "correlation_id": str(trace_id),
                "ts_ms": now_ts_ms(),
                "text": text,
                "session_id": session_id,
                "turn_id": turn_id,
                "edit": edit,
                "user_id": app["vars"].get("USER_ID"),
            },
            ensure_ascii=False,
        ).encode("utf-8"),
        timeout=NATS_REQUEST_TIMEOUT,
    )
    return json.loads(msg.data.decode("utf-8"))


async def handle_transcription(app, payload: dict):
    text = _clean_text(payload.get("text"))
    session_id = _clean_text(payload.get("session_id"))
    phrase_id = _clean_text(payload.get("phrase_id"))
    error_code = _clean_text(payload.get("error"))
    details = _clean_text(payload.get("details"))

    if error_code and not text:
        logger.warning("ASR error payload: %s", payload)
        await event_log(
            "log",
            "error",
            {"text": details or error_code},
            app=app,
            service=STACK_SERVICE_NAME,
        )
        await _publish_voice_block(app, False)
        return {"error": error_code, "details": details}

    if not text:
        logger.debug("Ignoring non-final ASR payload: %s", payload)
        return {}

    turn_id = _normalize_turn_id(payload.get("turn_id"), phrase_id)
    transcription_event: dict[str, object] = {
        "text": text,
        "turn_id": turn_id,
    }
    if session_id:
        transcription_event["session_id"] = session_id
    if phrase_id:
        transcription_event["phrase_id"] = phrase_id

    logger.info("ASR phrase committed: %r", text)
    await _publish_voice_block(app, True)
    await event_log(
        "command",
        "transcription",
        transcription_event,
        app=app,
        service=STACK_SERVICE_NAME,
    )

    try:
        return await _request_agent(
            app,
            text=text,
            session_id=session_id,
            turn_id=turn_id,
            edit=payload.get("edit"),
        )
    except Exception as exc:
        await event_log(
            "log",
            "error",
            {"text": f"Agent communication error: {str(exc)}"},
            app=app,
            service=STACK_SERVICE_NAME,
        )
        return {"error": "agent_communication", "details": str(exc)}
    finally:
        await _publish_voice_block(app, False)

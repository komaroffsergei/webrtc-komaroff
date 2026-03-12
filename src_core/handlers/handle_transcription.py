import json
import logging
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src_core.settings import STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log
from src_shared.contracts.common import now_ts_ms

logger = logging.getLogger("handle_transcription")


_PENDING_STATUSES = {"pending", "processing", "transcribing"}
_PENDING_EVENTS = {"pending"}
_TRANSCRIPTION_EVENT_TO_STATE = {
    "speech_started": "speech_started",
    "transcribing_started": "speech_started",
    "pending": "transcribing",
    "eof_sent": "transcribing",
    "final_received": "final_received",
    "thinking": "thinking",
    "idle": "idle",
    "asr_error": "error",
}


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


def _is_pending_payload(payload: dict) -> bool:
    if payload.get("pending") is True:
        return True
    status = _clean_text(payload.get("status"))
    if status and status.lower() in _PENDING_STATUSES:
        return True
    event = _clean_text(payload.get("event"))
    if event and event.lower() in _PENDING_EVENTS:
        return True
    return False


def _map_transcription_state(payload: dict) -> str | None:
    error_code = _clean_text(payload.get("error"))
    if error_code:
        return "error"
    event = _clean_text(payload.get("event"))
    if event:
        return _TRANSCRIPTION_EVENT_TO_STATE.get(event.lower())
    if _is_pending_payload(payload):
        return "transcribing"
    return None


def _state_message(state: str, payload: dict) -> str | None:
    details = _clean_text(payload.get("details"))
    if details and state == "error":
        return details
    if state == "speech_started":
        event = (_clean_text(payload.get("event")) or "").lower()
        if event == "transcribing_started":
            return "Передаю аудио в ASR"
        return "Слушаю"
    if state == "transcribing":
        event = (_clean_text(payload.get("event")) or "").lower()
        if event == "eof_sent":
            return "Жду финализацию распознавания"
        return "Распознаю речь"
    if state == "final_received":
        return "Финальная транскрипция получена"
    if state == "thinking":
        return "Отправляю реплику агенту"
    if state == "idle":
        return "Голосовой цикл завершён"
    if state == "error":
        error_code = _clean_text(payload.get("error"))
        if error_code:
            return error_code
    return None


async def _publish_voice_block(app, blocked: bool) -> None:
    await event_log(
        "command",
        "voice",
        {"blocked": blocked},
        app=app,
        service=STACK_SERVICE_NAME,
    )


async def _publish_transcription_log(
    app,
    *,
    state: str,
    payload: dict,
    session_id: str | None,
    phrase_id: str | None,
    turn_id: str | None,
    utterance_id: str | None,
) -> None:
    message = _state_message(state, payload)
    if not message:
        return
    data: dict[str, object] = {"text": message, "state": state}
    source_event = _clean_text(payload.get("event"))
    if session_id:
        data["session_id"] = session_id
    if phrase_id:
        data["phrase_id"] = phrase_id
    if turn_id:
        data["turn_id"] = turn_id
    if utterance_id:
        data["utterance_id"] = utterance_id
    if source_event:
        data["source_event"] = source_event
    await event_log(
        "log",
        "info",
        data,
        app=app,
        service=STACK_SERVICE_NAME,
    )


async def _publish_transcription_state(
    app,
    *,
    state: str,
    payload: dict,
    session_id: str | None,
    phrase_id: str | None,
    turn_id: str | None,
    utterance_id: str | None,
) -> None:
    data = {"state": state}
    source_event = _clean_text(payload.get("event"))
    message = _state_message(state, payload)
    if session_id:
        data["session_id"] = session_id
    if phrase_id:
        data["phrase_id"] = phrase_id
    if turn_id:
        data["turn_id"] = turn_id
    if utterance_id:
        data["utterance_id"] = utterance_id
    if source_event:
        data["source_event"] = source_event
    if message:
        data["message"] = message
    await event_log(
        "command",
        "transcription_state",
        data,
        app=app,
        service=STACK_SERVICE_NAME,
    )
    await _publish_transcription_log(
        app,
        state=state,
        payload=payload,
        session_id=session_id,
        phrase_id=phrase_id,
        turn_id=turn_id,
        utterance_id=utterance_id,
    )


async def handle_transcription(app, payload: dict):
    """Handle transcriptions and forward requests to the agent via NATS."""
    text = (payload.get("text") or "").strip()
    session_id = _clean_text(payload.get("session_id"))
    phrase_id = _clean_text(payload.get("phrase_id"))
    utterance_id = _clean_text(payload.get("utterance_id"))
    event_name = _clean_text(payload.get("event"))
    partial = _clean_text(payload.get("partial"))
    error_code = _clean_text(payload.get("error"))
    raw_turn_id = payload.get("turn_id")
    turn_id = _normalize_turn_id(raw_turn_id, phrase_id) if (raw_turn_id or phrase_id) else None
    state = _map_transcription_state(payload)
    is_asr_stream_payload = bool(
        phrase_id
        or utterance_id
        or event_name
        or payload.get("pending") is True
        or error_code
        or partial
    )

    if not text:
        if partial:
            return {"status": "partial"}
        if state:
            await _publish_transcription_state(
                app,
                state=state,
                payload=payload,
                session_id=session_id,
                phrase_id=phrase_id,
                turn_id=turn_id,
                utterance_id=utterance_id,
            )
            source_event = (event_name or "").lower()
            if state == "transcribing" and source_event != "transcribing_started":
                await _publish_voice_block(app, True)
            elif state == "error":
                await _publish_voice_block(app, False)
            elif state == "idle":
                await _publish_voice_block(app, False)
            return {"status": state}

        logger.warning("Empty transcription payload")
        return {}

    logger.info("handle_transcription: '%s'", text)

    effective_turn_id = turn_id or str(uuid4())
    if is_asr_stream_payload:
        await _publish_transcription_state(
            app=app,
            state="final_received",
            payload=payload,
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=turn_id,
            utterance_id=utterance_id,
        )
        transcription_event = {"text": text, "turn_id": effective_turn_id}
        if phrase_id:
            transcription_event["phrase_id"] = phrase_id
        if session_id:
            transcription_event["session_id"] = session_id
        if utterance_id:
            transcription_event["utterance_id"] = utterance_id
        await event_log(
            "command",
            "transcription",
            transcription_event,
            app=app,
            service=STACK_SERVICE_NAME,
        )
        await _publish_transcription_state(
            app=app,
            state="thinking",
            payload={"event": "thinking"},
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=turn_id,
            utterance_id=utterance_id,
        )
        await _publish_voice_block(app, True)

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
                "turn_id": effective_turn_id,
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
        if is_asr_stream_payload:
            await _publish_transcription_state(
                app=app,
                state="error",
                payload={"error": "agent_communication", "details": str(e)},
                session_id=session_id,
                phrase_id=phrase_id,
                turn_id=turn_id,
                utterance_id=utterance_id,
            )
        return {"error": "agent_communication", "details": str(e)}
    finally:
        if is_asr_stream_payload:
            try:
                await _publish_voice_block(app, False)
                await _publish_transcription_state(
                    app=app,
                    state="idle",
                    payload={"event": "idle"},
                    session_id=session_id,
                    phrase_id=phrase_id,
                    turn_id=turn_id,
                    utterance_id=utterance_id,
                )
            except Exception:
                logger.exception("Failed to publish voice lifecycle events")

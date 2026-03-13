import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from src_core.settings import LIVE_ASR_COMMIT_IDLE_MS, STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log
from src_shared.contracts.common import now_ts_ms

logger = logging.getLogger("handle_transcription")


_PENDING_STATUSES = {"pending", "processing", "transcribing"}
_PENDING_EVENTS = {"pending"}
_TRANSCRIPTION_EVENT_TO_STATE = {
    "pending": "transcribing",
    "thinking": "thinking",
    "idle": "idle",
    "asr_error": "error",
}


@dataclass(slots=True)
class LiveAsrSessionState:
    session_id: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    segments: list[str] = field(default_factory=list)
    partial: str | None = None
    last_phrase_id: str | None = None
    last_utterance_id: str | None = None
    commit_task: asyncio.Task | None = None
    transcribing: bool = False
    locked: bool = False


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
    if state == "transcribing":
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


async def _publish_raw_linto_log(
    app,
    *,
    payload: dict,
    session_id: str | None,
    phrase_id: str | None,
    turn_id: str | None,
    utterance_id: str | None,
    event_name: str | None,
    error_code: str | None,
) -> None:
    if "raw_linto" not in payload and "raw_linto_text" not in payload:
        return
    data: dict[str, object] = {}
    if session_id:
        data["session_id"] = session_id
    if phrase_id:
        data["phrase_id"] = phrase_id
    if turn_id:
        data["turn_id"] = turn_id
    if utterance_id:
        data["utterance_id"] = utterance_id
    if event_name:
        data["source_event"] = event_name
    if "raw_linto" in payload:
        data["raw_linto"] = payload.get("raw_linto")
    if "raw_linto_text" in payload:
        data["raw_linto_text"] = payload.get("raw_linto_text")
    kind = "error" if error_code else "info"
    await event_log(
        "log",
        kind,
        data,
        name="asr_linto_raw",
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


def _get_live_asr_sessions(app) -> dict[str, LiveAsrSessionState]:
    sessions = app.get("live_asr_sessions")
    if isinstance(sessions, dict):
        return sessions
    sessions = {}
    app["live_asr_sessions"] = sessions
    return sessions


def _get_live_asr_session(app, session_id: str) -> LiveAsrSessionState:
    sessions = _get_live_asr_sessions(app)
    state = sessions.get(session_id)
    if state is None:
        state = LiveAsrSessionState(session_id=session_id)
        sessions[session_id] = state
    return state


def _drop_live_asr_session(app, session_id: str, state: LiveAsrSessionState | None = None) -> None:
    sessions = _get_live_asr_sessions(app)
    existing = sessions.get(session_id)
    if existing is None:
        return
    if state is not None and existing is not state:
        return
    sessions.pop(session_id, None)


def _cancel_commit_task(state: LiveAsrSessionState) -> None:
    task = state.commit_task
    state.commit_task = None
    if task and not task.done():
        task.cancel()


def _live_asr_commit_idle_s(app) -> float:
    raw = app.get("vars", {}).get("LIVE_ASR_COMMIT_IDLE_MS", LIVE_ASR_COMMIT_IDLE_MS)
    try:
        idle_ms = float(raw)
    except Exception:
        idle_ms = float(LIVE_ASR_COMMIT_IDLE_MS)
    return max(0.1, idle_ms / 1000.0)


def _join_live_segments(segments: list[str]) -> str:
    joined = " ".join(part.strip() for part in segments if part.strip())
    return re.sub(r"\s+", " ", joined).strip()


def _is_live_stream_payload(
    *,
    session_id: str | None,
    phrase_id: str | None,
    utterance_id: str | None,
    event_name: str | None,
    partial: str | None,
    error_code: str | None,
) -> bool:
    return bool(
        session_id
        and (phrase_id or utterance_id or event_name or partial or error_code)
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
    return json.loads(msg.data.decode("utf-8"))


async def _commit_live_asr_after_idle(
    app,
    *,
    session_id: str,
    state: LiveAsrSessionState,
    delay_s: float,
) -> None:
    try:
        await asyncio.sleep(delay_s)
        await _commit_live_asr_buffer(app, session_id=session_id, state=state)
    except asyncio.CancelledError:
        return
    except Exception:
        logger.exception("Live ASR debounce commit failed for session_id=%s", session_id)


async def _schedule_live_asr_commit(app, *, session_id: str, state: LiveAsrSessionState) -> None:
    _cancel_commit_task(state)
    delay_s = _live_asr_commit_idle_s(app)
    state.commit_task = asyncio.create_task(
        _commit_live_asr_after_idle(app, session_id=session_id, state=state, delay_s=delay_s)
    )


async def _commit_live_asr_buffer(
    app,
    *,
    session_id: str,
    state: LiveAsrSessionState,
) -> None:
    async with state.lock:
        if state.locked:
            return
        current_task = asyncio.current_task()
        if state.commit_task is current_task or (state.commit_task is not None and state.commit_task.done()):
            state.commit_task = None

        text = _join_live_segments(state.segments)
        phrase_id = state.last_phrase_id
        utterance_id = state.last_utterance_id
        had_activity = state.transcribing or bool(state.partial) or bool(state.segments)

        state.partial = None
        state.segments.clear()
        state.last_phrase_id = None
        state.last_utterance_id = None
        state.transcribing = False

        if not text:
            state.locked = False
        else:
            state.locked = True

    if not had_activity:
        _drop_live_asr_session(app, session_id, state)
        return

    if not text:
        await _publish_voice_block(app, False)
        await _publish_transcription_state(
            app=app,
            state="idle",
            payload={"event": "idle"},
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=None,
            utterance_id=utterance_id,
        )
        _drop_live_asr_session(app, session_id, state)
        return

    turn_id = str(uuid4())
    await _publish_transcription_state(
        app=app,
        state="final_received",
        payload={"event": "final_received"},
        session_id=session_id,
        phrase_id=phrase_id,
        turn_id=turn_id,
        utterance_id=utterance_id,
    )

    transcription_event: dict[str, object] = {"text": text, "turn_id": turn_id}
    if session_id:
        transcription_event["session_id"] = session_id
    if phrase_id:
        transcription_event["phrase_id"] = phrase_id
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
        await _request_agent(
            app,
            text=text,
            session_id=session_id,
            turn_id=turn_id,
            edit=None,
        )
    except Exception as exc:
        await event_log(
            "log",
            "error",
            {"text": f"Agent communication error: {str(exc)}"},
            app=app,
            service=STACK_SERVICE_NAME,
        )
        await _publish_transcription_state(
            app=app,
            state="error",
            payload={"error": "agent_communication", "details": str(exc)},
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=turn_id,
            utterance_id=utterance_id,
        )
    finally:
        async with state.lock:
            state.locked = False
            state.partial = None
            state.segments.clear()
            state.last_phrase_id = None
            state.last_utterance_id = None
            state.commit_task = None
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
        finally:
            _drop_live_asr_session(app, session_id, state)


async def _handle_live_asr_payload(
    app,
    *,
    payload: dict,
    text: str | None,
    session_id: str,
    phrase_id: str | None,
    utterance_id: str | None,
    event_name: str | None,
    partial: str | None,
    error_code: str | None,
    turn_id: str | None,
) -> dict:
    state = _get_live_asr_session(app, session_id)

    await _publish_raw_linto_log(
        app,
        payload=payload,
        session_id=session_id,
        phrase_id=phrase_id,
        turn_id=turn_id,
        utterance_id=utterance_id,
        event_name=event_name,
        error_code=error_code,
    )

    if error_code:
        async with state.lock:
            _cancel_commit_task(state)
            state.partial = None
            state.segments.clear()
            state.last_phrase_id = None
            state.last_utterance_id = None
            state.transcribing = False
            state.locked = False
        await _publish_transcription_state(
            app,
            state="error",
            payload=payload,
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=turn_id,
            utterance_id=utterance_id,
        )
        await _publish_voice_block(app, False)
        _drop_live_asr_session(app, session_id, state)
        return {"status": "error"}

    if state.locked:
        logger.info("Ignoring live ASR payload while session %s is waiting for agent", session_id)
        return {"status": "locked"}

    if not text and not partial:
        legacy_state = _map_transcription_state(payload)
        if legacy_state:
            await _publish_transcription_state(
                app,
                state=legacy_state,
                payload=payload,
                session_id=session_id,
                phrase_id=phrase_id,
                turn_id=turn_id,
                utterance_id=utterance_id,
            )
            if legacy_state in {"idle", "error"}:
                await _publish_voice_block(app, False)
                _drop_live_asr_session(app, session_id, state)
            return {"status": legacy_state}
        return {}

    publish_transcribing = False
    async with state.lock:
        if not state.transcribing:
            state.transcribing = True
            publish_transcribing = True
        if partial:
            state.partial = partial
        if text:
            state.segments.append(text)
            state.partial = None
        if phrase_id:
            state.last_phrase_id = phrase_id
        if utterance_id:
            state.last_utterance_id = utterance_id
        await _schedule_live_asr_commit(app, session_id=session_id, state=state)

    if publish_transcribing:
        await _publish_transcription_state(
            app,
            state="transcribing",
            payload={"event": "pending"},
            session_id=session_id,
            phrase_id=phrase_id,
            turn_id=turn_id,
            utterance_id=utterance_id,
        )
        await _publish_voice_block(app, True)

    if text:
        return {"status": "buffered"}
    return {"status": "partial"}


async def handle_transcription(app, payload: dict):
    """Handle text messages immediately and buffer live ASR segments until silence."""
    text = _clean_text(payload.get("text"))
    session_id = _clean_text(payload.get("session_id"))
    phrase_id = _clean_text(payload.get("phrase_id"))
    utterance_id = _clean_text(payload.get("utterance_id"))
    event_name = _clean_text(payload.get("event"))
    partial = _clean_text(payload.get("partial"))
    error_code = _clean_text(payload.get("error"))
    raw_turn_id = payload.get("turn_id")
    turn_id = _normalize_turn_id(raw_turn_id, phrase_id) if (raw_turn_id or phrase_id) else None
    is_asr_stream_payload = _is_live_stream_payload(
        session_id=session_id,
        phrase_id=phrase_id,
        utterance_id=utterance_id,
        event_name=event_name,
        partial=partial,
        error_code=error_code,
    )

    if is_asr_stream_payload:
        return await _handle_live_asr_payload(
            app,
            payload=payload,
            text=text,
            session_id=session_id,
            phrase_id=phrase_id,
            utterance_id=utterance_id,
            event_name=event_name,
            partial=partial,
            error_code=error_code,
            turn_id=turn_id,
        )

    if not text:
        logger.warning("Empty transcription payload")
        return {}

    logger.info("handle_transcription: '%s'", text)

    effective_turn_id = turn_id or str(uuid4())
    try:
        response = await _request_agent(
            app,
            text=text,
            session_id=session_id,
            turn_id=effective_turn_id,
            edit=payload.get("edit"),
        )
        return response
    except Exception as exc:
        await event_log(
            "log",
            "error",
            {"text": f"Agent communication error: {str(exc)}"},
            app=app,
            service=STACK_SERVICE_NAME,
        )
        return {"error": "agent_communication", "details": str(exc)}

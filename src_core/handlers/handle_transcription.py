import json
import logging
from uuid import uuid4

from src_core.settings import STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log
from src_shared.contracts.common import now_ts_ms

logger = logging.getLogger("handle_transcription")


async def handle_transcription(app, payload: dict):
    """Handle transcriptions and forward requests to the agent via NATS."""
    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return {}

    logger.info("handle_transcription: '%s'", text)

    session_id = payload.get("session_id")
    phrase_id = payload.get("phrase_id")
    if phrase_id:
        await event_log(
            "command",
            "transcription",
            {"text": text, "phrase_id": phrase_id},
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

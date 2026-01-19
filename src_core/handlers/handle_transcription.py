import json
import logging

from src_core.settings import STACK_SERVICE_NAME, NATS_REQUEST_TIMEOUT
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_transcription")


async def handle_transcription(app, payload: dict):
    """Обработчик транскрипций, отправляющий запросы агенту через NATS"""
    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    logger.info("handle_transcription: '%s'", text)

    try:
        nc = app['services']['nats_client']
        session_id = payload.get("session_id")
        edit = payload.get("edit")
        msg = await nc.request(
            app['vars']['NATS_AGENT_SUBJECT'],
            json.dumps({
                "text": text,
                "session_id": session_id,
                "edit": edit,
            }, ensure_ascii=False).encode("utf-8"),
            timeout=NATS_REQUEST_TIMEOUT,
        )

        response = json.loads(msg.data.decode("utf-8"))
        await event_log(response,
                        kind="message",
                        app=app,
                        service=STACK_SERVICE_NAME)

    except Exception as e:
        await event_log(f"Agent communication error: {str(e)}",
                        kind="error",
                        app=app,
                        service=STACK_SERVICE_NAME)

import json
import logging

from src_core.settings import NATS_AGENT_SUBJECT, STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_transcription")


async def handle_transcription(app, payload: dict):
    """Обработчик транскрипций, отправляющий запросы агенту через NATS"""
    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    # await event_log(message=text, kind="message", app=app, service=STACK_SERVICE_NAME)
    logger.info("handle_transcription: '%s'", text)

    try:
        nc = app['services']['nats_client']
        msg = await nc.request(
            app['vars']['NATS_AGENT_SUBJECT'],
            json.dumps({
                "text": text
            }, ensure_ascii=False).encode("utf-8"),
            timeout=120.0,
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

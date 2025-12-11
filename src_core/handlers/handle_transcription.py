import json
import logging

from src_core.settings import NATS_AGENT_SUBJECT, STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_transcription")


# ... (импорты остаются)

async def handle_transcription(app, payload: dict):
    """Обработчик транскрипций, отправляющий запросы агенту через NATS"""
    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    await event_log(
        {
            "type": "user_message",
            "service": "ai_agent",
            "message": text
        },
        level="info",
        app=app
    )

    logger.info("handle_transcription: '%s'", text)

    # Отправляем запрос агенту через NATS
    try:
        nc = app['services']['nats_client']
        request_payload = {
            "text": text,
            "service": STACK_SERVICE_NAME
        }

        msg = await nc.request(
            app['vars']['NATS_AGENT_SUBJECT'],
            json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            timeout=120.0,  # увеличенный таймаут для сложных запросов
        )

        response = json.loads(msg.data.decode("utf-8"))

        if response.get("status") == "success":
            result = response.get("result", "")
            await event_log(result, level="info", name="message", app=app)
        else:
            error = response.get("error", "Unknown error")
            await event_log(f"Agent error: {error}", level="error", name="agent_error", app=app)

    except Exception as e:
        logger.error("Agent request failed: %s", e, exc_info=True)
        await event_log(f"Agent communication error: {str(e)}", level="error", name="agent_error", app=app)

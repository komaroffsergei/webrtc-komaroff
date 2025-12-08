import json
import logging

from src_core.server.utils.sse import sse_log, SSEContext, register_sse_context

logger = logging.getLogger("handle_transcription")


# ... (импорты остаются)

async def handle_transcription(app, payload: dict):
    """Обработчик транскрипций, отправляющий запросы агенту через NATS"""
    text = (payload.get("text") or "").strip()
    if not text:
        logger.warning("Empty transcription payload")
        return

    await sse_log(
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
            "service": app['vars']["STACK_SERVICE_NAME"]
        }

        # Используем NATS subjects из настроек
        agent_subject = app['vars'].get("NATS_AGENT_SUBJECT", "agent.requests")

        msg = await nc.request(
            agent_subject,
            json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
            timeout=120.0,  # увеличенный таймаут для сложных запросов
        )

        response = json.loads(msg.data.decode("utf-8"))

        if response.get("status") == "success":
            result = response.get("result", "")
            await sse_log(result, level="info", name="message", app=app)
        else:
            error = response.get("error", "Unknown error")
            await sse_log(f"Agent error: {error}", level="error", name="agent_error", app=app)

    except Exception as e:
        logger.error("Agent request failed: %s", e, exc_info=True)
        await sse_log(f"Agent communication error: {str(e)}", level="error", name="agent_error", app=app)
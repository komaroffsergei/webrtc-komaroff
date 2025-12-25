import logging
from aiohttp import web

from src_core.handlers.handle_transcription import handle_transcription
from src_core.settings import STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_message")


async def message_handler(request: web.Request):
    """
    Обработчик POST /message для приема сообщений от клиента.
    
    Ожидаемый формат:
    {
        "text": "текст сообщения от клиента"
    }
    
    Отправляет подтверждение через SSE и возвращает echo ответ клиенту.
    """
    try:
        data = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON: {e}")
        return web.json_response({"error": "Invalid JSON"}, status=400)

    text = data.get("text", "").strip()
    if not text:
        return web.json_response({"error": "text field is required"}, status=400)

    await event_log(text,
                    kind="log",
                    app=request.app,
                    service=STACK_SERVICE_NAME)

    await handle_transcription(request.app, {"text": text})

    return web.json_response({
        "status": "ok",
    })

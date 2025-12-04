import logging
from aiohttp import web

from src_core.server.handlers.handle_transcription import handle_transcription
from src_core.server.settings import STACK_SERVICE_NAME
from src_core.server.utils.sse import sse_log, SSEContext, register_sse_context

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

    message_uid = await sse_log(text, level='info', app=request.app)
    
    logger.info(f"Message received: {text[:50]}... (uid={message_uid})")
    
    # Отправляем ответ клиенту через SSE
    await sse_log(f"Эхо: {text}", level='info', app=request.app)
    await handle_transcription(request.app, {"text": text})

    return web.json_response({
        "status": "ok",
        "uid": message_uid
    })

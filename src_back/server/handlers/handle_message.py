import logging
from aiohttp import web

from src_back.server.utils.sse import sse_log

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
    
    # Отправляем подтверждение получения через SSE
    message_uid = await sse_log(request.app, text, 'info')
    
    logger.info(f"Message received: {text[:50]}... (uid={message_uid})")
    
    # Отправляем ответ клиенту через SSE
    await sse_log(request.app, f"Эхо: {text}", 'info')
    
    return web.json_response({
        "status": "ok",
        "uid": message_uid
    })

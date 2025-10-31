import logging
import uuid
from aiohttp import web

from .sse import sse_broadcast

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
    
    message_uid = str(uuid.uuid4())
    
    # Отправляем подтверждение получения через SSE
    await sse_broadcast(request.app, {
        "type": "message",
        "descr": "received",
        "uid": message_uid,
        "text": text
    })
    
    logger.info(f"Message received: {text[:50]}... (uid={message_uid})")
    
    # Отправляем ответ клиенту через SSE
    response_uid = str(uuid.uuid4())
    await sse_broadcast(request.app, {
        "type": "message",
        "descr": "send",
        "uid": response_uid,
        "text": f"Эхо: {text}"
    })
    
    return web.json_response({
        "status": "ok",
        "uid": message_uid
    })

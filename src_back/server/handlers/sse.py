from aiohttp import web
import asyncio
import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("sse")


async def sse_handler(request: web.Request):
    """
    Единый SSE endpoint для всех типов сообщений от сервера к клиенту.
    Обрабатывает: команды, логи, сообщения, предупреждения.
    """
    resp = web.StreamResponse(status=200, reason="OK", headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    })
    await resp.prepare(request)
    q = asyncio.Queue(maxsize=100)
    request.app.setdefault("sse_clients", set()).add(q)
    
    # Отправляем приветственное сообщение после добавления в clients
    asyncio.create_task(_send_welcome_log(request.app))
    
    try:
        while True:
            msg = await q.get()
            try:
                data = json.dumps(msg, ensure_ascii=False)
            except Exception:
                data = "{}"
            
            try:
                await resp.write(f"data: {data}\n\n".encode("utf-8"))
                await resp.drain()
            except (ConnectionResetError, ConnectionError, BrokenPipeError):
                # Клиент отключился, выходим из цикла
                logger.debug("SSE client disconnected")
                break
            except Exception as e:
                logger.warning(f"Error writing to SSE stream: {e}")
                break
                
    except asyncio.CancelledError:
        logger.debug("SSE handler cancelled")
    finally:
        try:
            request.app["sse_clients"].discard(q)
        except Exception:
            pass
    return resp


async def _send_welcome_log(app):
    """Отправить приветственное сообщение после небольшой задержки"""
    await asyncio.sleep(0.1)
    await sse_log(app, "SSE connection established", level="info", category="system")


async def sse_broadcast(app, message: dict):
    """
    Базовая функция отправки SSE сообщений всем подключенным клиентам.
    Используется внутренне специализированными функциями.
    """
    # Добавляем timestamp если его нет
    if "timestamp" not in message:
        message["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    # Добавляем uid если его нет
    if "uid" not in message:
        message["uid"] = str(uuid.uuid4())
    
    for q in list(app.get("sse_clients", [])):
        try:
            q.put_nowait(message)
        except asyncio.QueueFull:
            # Drop oldest message if queue is full
            try:
                q.get_nowait()
                q.put_nowait(message)
            except Exception:
                pass
        except Exception:
            pass


async def sse_command(app, method: str, params=None, uid: str = None):
    """
    Отправить команду клиенту.
    
    Args:
        app: aiohttp application
        method: имя метода команды
        params: параметры команды (любой JSON-сериализуемый тип)
        uid: опциональный uid (будет сгенерирован если не указан)
    
    Returns:
        str: uid команды
    """
    if uid is None:
        uid = str(uuid.uuid4())
    
    await sse_broadcast(app, {
        "type": "command",
        "method": method,
        "params": params,
        "uid": uid
    })
    
    logger.debug(f"SSE command sent: method={method}, uid={uid}")
    return uid


async def sse_message(app, text: str, descr: str = "send", uid: str = None, **extra):
    """
    Отправить текстовое сообщение клиенту.
    
    Args:
        app: aiohttp application
        text: текст сообщения
        descr: описание ('send' для исходящих, 'received' для подтверждения)
        uid: опциональный uid
        **extra: дополнительные поля для сообщения
    
    Returns:
        str: uid сообщения
    """
    if uid is None:
        uid = str(uuid.uuid4())
    
    message = {
        "type": "message",
        "descr": descr,
        "uid": uid,
        "text": text
    }
    message.update(extra)
    
    await sse_broadcast(app, message)
    
    logger.debug(f"SSE message sent: descr={descr}, uid={uid}")
    return uid


async def sse_log(app, message: str, level: str = "info", category: str = "general", **extra):
    """
    Отправить лог-сообщение клиенту для отладочного окна.
    
    Args:
        app: aiohttp application
        message: текст лога
        level: уровень логирования ('debug', 'info', 'warning', 'error')
        category: категория лога ('system', 'webrtc', 'nats', 'audio', 'general')
        **extra: дополнительные поля
    
    Returns:
        str: uid лога
    """
    uid = str(uuid.uuid4())
    
    log_entry = {
        "type": "log",
        "level": level,
        "category": category,
        "message": message,
        "uid": uid
    }
    log_entry.update(extra)
    
    await sse_broadcast(app, log_entry)
    
    return uid


async def sse_warning(app, descr: str, uid: str = None):
    """
    Отправить предупреждение клиенту.
    
    Args:
        app: aiohttp application
        descr: тип предупреждения ('mic_too_loud', 'mic_too_quiet', 'mic_too_noise')
        uid: опциональный uid
    
    Returns:
        str: uid предупреждения
    """
    if uid is None:
        uid = str(uuid.uuid4())
    
    await sse_broadcast(app, {
        "type": "warning",
        "descr": descr,
        "uid": uid
    })
    
    logger.debug(f"SSE warning sent: descr={descr}, uid={uid}")
    return uid

from __future__ import annotations

from aiohttp import web
import asyncio
import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("sse")

DEFAULT_SERVICE_NAME = "src_back"


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

    asyncio.create_task(request.app.handle_startup_sse(request))
    
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

async def sse_broadcast(app, message: dict, ensure_meta: bool = True):
    """
    Базовая функция отправки SSE сообщений всем подключенным клиентам.
    Используется внутренне специализированными функциями.
    """
    payload = dict(message)

    if ensure_meta:
        if "timestamp" not in payload:
            payload["timestamp"] = datetime.utcnow().isoformat() + "Z"
        
        if "uid" not in payload:
            payload["uid"] = str(uuid.uuid4())
        
        if not payload.get("service"):
            payload["service"] = DEFAULT_SERVICE_NAME

    for q in list(app.get("sse_clients", [])):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            # Drop oldest message if queue is full
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass
        except Exception:
            pass


async def sse_log(app, message: str, level: str = "info", service: str = DEFAULT_SERVICE_NAME, *, log_time: str | None = None):
    """
    Отправить лог-сообщение клиенту для отладочного окна в упрощенном формате.
    """
    log_entry = {
        "time": log_time or datetime.utcnow().isoformat(),
        "service": service,
        "type": level,
        "message": message,
    }

    await sse_broadcast(app, log_entry, ensure_meta=False)
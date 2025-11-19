from __future__ import annotations

from aiohttp import web
import asyncio
import json
import logging
import uuid
from datetime import datetime

logger = logging.getLogger("sse")

DEFAULT_SERVICE_NAME = "src_back"


# async def init_sse(request: web.Request):
#     resp = web.StreamResponse(status=200, reason="OK", headers={
#         "Content-Type": "text/event-stream",
#         "Cache-Control": "no-cache",
#         "Connection": "keep-alive",
#         "Access-Control-Allow-Origin": "*",
#     })
#     await resp.prepare(request)
#     q = asyncio.Queue(maxsize=100)
#     request.app.setdefault("sse_clients", set()).add(q)
async def sse_handler(request: web.Request):
    app = request.app
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        },
    )
    await resp.prepare(request)

    q = asyncio.Queue(maxsize=100)
    app["sse_clients"].add(q)

    logger.info("SSE client connected, total=%s", len(app["sse_clients"]))

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
                logger.debug("SSE client disconnected")
                break
            except Exception as e:
                logger.warning(f"Error writing to SSE stream: {e}")
                break
    except asyncio.CancelledError:
        logger.debug("SSE handler cancelled")
    finally:
        app["sse_clients"].discard(q)
        logger.info("SSE client removed, total=%s", len(app["sse_clients"]))

    return resp


async def sse_broadcast(app, message, ensure_meta: bool = True):
    if not isinstance(message, dict):
        message = {"msg": str(message)}

    payload = dict(message)

    if ensure_meta:
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        payload.setdefault("uid", str(uuid.uuid4()))
        payload.setdefault("service", DEFAULT_SERVICE_NAME)

    clients = list(app.get("sse_clients", []))
    if not clients:
        logger.debug("No SSE clients, dropping: %s", payload)
        return

    for q in clients:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                pass
        except Exception as e:
            logger.warning("Error putting to SSE queue: %s", e)


async def sse_log(app, message: str, level: str = "info", service: str = DEFAULT_SERVICE_NAME, *,
                  log_time: str | None = None, name: str = None):
    """
    Отправить лог-сообщение клиенту для отладочного окна в упрощенном формате.
    """
    log_entry = {
        "time": log_time or datetime.utcnow().isoformat(),
        "service": service,
        "type": level,
        "name": name or "",
        "message": message,
    }

    await sse_broadcast(app, log_entry, ensure_meta=False)


def make_async_callback(loop, async_func, app):
    def callback(status):
        loop.call_soon_threadsafe(
            asyncio.create_task,
            async_func(app, status)
        )

    return callback

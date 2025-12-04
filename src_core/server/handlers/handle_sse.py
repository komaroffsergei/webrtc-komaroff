import asyncio
import json
import logging
import uuid
from datetime import datetime

from aiohttp import web
from aiohttp.web_app import Application

from src_core.main import STACK_SERVICE_NAME

logger = logging.getLogger("handle_sse")

async def sse_handler(request: web.Request):
    """
    SSE endpoint. Each client gets its own small queue.
    Slow clients are dropped automatically so they don't block others.
    """

    app = request.app

    # Proper SSE headers
    resp = web.StreamResponse(
        status=200,
        reason="OK",
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "X-Accel-Buffering": "no",  # avoid nginx buffering
        },
    )
    await resp.prepare(request)

    # Each client gets its own tiny queue
    # maxsize=1 ensures slow clients cannot block the system
    q = asyncio.Queue(maxsize=1)
    app['sse_clients'].add(q)

    logger.info("SSE client connected, total=%s", len(app['sse_clients']))

    try:
        while True:
            # Wait for a message pushed by sse_broadcast
            msg = await q.get()

            try:
                data = json.dumps(msg, ensure_ascii=False)
            except Exception:
                data = "{}"

            try:
                # Send event to the browser
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
        # Clean up the client
        app['sse_clients'].discard(q)
        logger.info("SSE client removed, total=%s", len(app['sse_clients']))

    return resp


def make_async_callback(loop, async_func, app):
    """
    Convert a synchronous callback into an async executor-safe callback.
    Used for thread-safe status updates (e.g., model loading).
    """

    def callback(status):
        loop.call_soon_threadsafe(
            asyncio.create_task,
            async_func(app, status)
        )

    return callback



async def sse_broadcast(app: Application, message, *, ensure_meta: bool = True):
    if not isinstance(message, dict):
        message = {"msg": str(message)}

    payload = dict(message)

    if ensure_meta:
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        payload.setdefault("uid", str(uuid.uuid4()))
        payload.setdefault("service", STACK_SERVICE_NAME)


    if not app['clients']:
        logger.debug("No SSE clients, dropping: %s", payload)
        return

    for q in app['clients']:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                app['clients'].discard(q)
        except Exception:
            app['clients'].discard(q)


async def sse_log(
    app: Application,
    message: str,
    level: str = "info",
    *,
    service: str | None = None,
    log_time: str | None = None,
    name: str | None = None,
):
    entry = {
        "time": log_time or datetime.utcnow().isoformat(),
        "service": service or STACK_SERVICE_NAME,
        "type": level,
        "name": name or "",
        "message": message,
    }
    await sse_broadcast(app, entry, ensure_meta=False)

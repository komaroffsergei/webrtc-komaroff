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
    app["sse_clients"].add(q)

    logger.info("SSE client connected, total=%s", len(app["sse_clients"]))

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
        app["sse_clients"].discard(q)
        logger.info("SSE client removed, total=%s", len(app["sse_clients"]))

    return resp


async def sse_broadcast(app, message, ensure_meta: bool = True):
    """
    Broadcast message to all connected SSE clients.
    Slow clients are dropped automatically using non-blocking put_nowait().
    """

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
            # Non-blocking put
            q.put_nowait(payload)

        except asyncio.QueueFull:
            # Slow client: remove oldest and push newest,
            # or drop entire client if needed
            try:
                q.get_nowait()
                q.put_nowait(payload)
            except Exception:
                # If the client is completely stuck, drop it
                app["sse_clients"].discard(q)

        except Exception as e:
            logger.warning("Error putting to SSE queue: %s", e)
            app["sse_clients"].discard(q)


async def sse_log(
    app,
    message: str,
    level: str = "info",
    service: str = DEFAULT_SERVICE_NAME,
    *,
    log_time: str | None = None,
    name: str = None
):
    """
    Send a simple log entry to SSE clients.
    Used for lightweight debugging messages in UI.
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

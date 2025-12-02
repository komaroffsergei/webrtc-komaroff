from __future__ import annotations

from aiohttp import web
import asyncio
import json
import logging

from shared.sse import SSEContext

logger = logging.getLogger("sse")


def register_sse_context(app, context: SSEContext):
    app["sse_context"] = context


def get_sse_context(app) -> SSEContext:
    context = app.get("sse_context")
    if context is None:
        raise RuntimeError("SSE context is not initialized")
    return context


async def sse_handler(request: web.Request):
    """
    SSE endpoint. Each client gets its own small queue.
    Slow clients are dropped automatically so they don't block others.
    """

    app = request.app
    context = get_sse_context(app)

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
    context.clients.add(q)

    logger.info("SSE client connected, total=%s", len(context.clients))

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
        context.clients.discard(q)
        logger.info("SSE client removed, total=%s", len(context.clients))

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

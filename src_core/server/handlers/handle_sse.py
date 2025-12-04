import asyncio
import json
import logging

from aiohttp import web

from src_core.server.utils.sse import get_sse_context

logger = logging.getLogger("handle_sse")

async def sse_handler(request: web.Request):
    """
    SSE endpoint. Each client gets its own small queue.
    Slow clients are dropped automatically so they don't block others.
    """

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

    # Each client gets its own tiny queue; maxsize=1 prevents slow consumers from blocking others
    ctx = get_sse_context(request.app)
    q = ctx.register_client()

    logger.info("SSE client connected, total=%s", len(ctx))

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
        ctx.discard_client(q)
        logger.info("SSE client removed, total=%s", len(ctx))

    return resp

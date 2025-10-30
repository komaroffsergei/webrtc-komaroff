from aiohttp import web
import asyncio
import json
import logging

logger = logging.getLogger("sse")


async def sse_handler(request: web.Request):
    resp = web.StreamResponse(status=200, reason="OK", headers={
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "Access-Control-Allow-Origin": "*",
    })
    await resp.prepare(request)
    q = asyncio.Queue(maxsize=100)
    request.app.setdefault("sse_clients", set()).add(q)
    try:
        while True:
            msg = await q.get()
            try:
                data = json.dumps(msg, ensure_ascii=False)
            except Exception:
                data = "{}"
            await resp.write(f"data: {data}\n\n".encode("utf-8"))
            await resp.drain()
    except asyncio.CancelledError:
        pass
    finally:
        try:
            request.app["sse_clients"].discard(q)
        except Exception:
            pass
    return resp


async def sse_broadcast(app, message: dict):
    for q in list(app.get("sse_clients", [])):
        try:
            q.put_nowait(message)
        except Exception:
            pass

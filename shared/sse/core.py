import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Set

logger = logging.getLogger("shared.sse")

DEFAULT_SERVICE_NAME = "service"


@dataclass
class SSEContext:
    service_name: str = DEFAULT_SERVICE_NAME
    clients: Set[asyncio.Queue] = field(default_factory=set)


async def sse_broadcast(context: SSEContext, message, *, ensure_meta: bool = True):
    if not isinstance(message, dict):
        message = {"msg": str(message)}

    payload = dict(message)

    if ensure_meta:
        payload.setdefault("timestamp", datetime.utcnow().isoformat())
        payload.setdefault("uid", str(uuid.uuid4()))
        payload.setdefault("service", context.service_name)

    clients = list(context.clients)
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
                context.clients.discard(q)
        except Exception:
            context.clients.discard(q)


async def sse_log(
    context: SSEContext,
    message: str,
    level: str = "info",
    *,
    service: str | None = None,
    log_time: str | None = None,
    name: str | None = None,
):
    entry = {
        "time": log_time or datetime.utcnow().isoformat(),
        "service": service or context.service_name,
        "type": level,
        "name": name or "",
        "message": message,
    }
    await sse_broadcast(context, entry, ensure_meta=False)

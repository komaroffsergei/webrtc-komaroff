from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, MutableMapping

from aiohttp.web_app import Application

logger = logging.getLogger("sse")


class SSEContext:
    """Stores connected SSE clients and handles broadcasts."""

    def __init__(self, *, service_name: str) -> None:
        self.service_name = service_name
        self._clients: set[asyncio.Queue] = set()

    def register_client(self) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._clients.add(queue)
        return queue

    def discard_client(self, queue: asyncio.Queue) -> None:
        self._clients.discard(queue)

    def __len__(self) -> int:
        return len(self._clients)

    async def broadcast(self, message: Any, *, ensure_meta: bool = True) -> str | None:
        payload = prepare_payload(message, self.service_name, ensure_meta=ensure_meta)
        if not self._clients:
            logger.debug("No SSE clients, dropping: %s", payload)
            return payload.get("uid")

        for queue in list(self._clients):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                    queue.put_nowait(payload)
                except Exception:
                    self._clients.discard(queue)
            except Exception:
                self._clients.discard(queue)
        return payload.get("uid")

    async def log(
        self,
        message: Any,
        *,
        level: str = "info",
        service: str | None = None,
        log_time: str | None = None,
        name: str | None = None,
    ) -> str:
        entry = {
            "time": log_time or utc_now(),
            "service": service or self.service_name,
            "type": level,
            "name": name or "",
            "message": message,
            "uid": str(uuid.uuid4()),
        }
        await self.broadcast(entry, ensure_meta=False)
        return entry["uid"]


def prepare_payload(message: Any, service_name: str, *, ensure_meta: bool) -> dict:
    if isinstance(message, Mapping):
        payload: MutableMapping[str, Any] = dict(message)
    else:
        payload = {"message": str(message)}

    if ensure_meta:
        payload.setdefault("timestamp", utc_now())
        payload.setdefault("uid", str(uuid.uuid4()))
        payload.setdefault("service", service_name)
    return dict(payload)


def utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds")


_DEFAULT_CONTEXT: SSEContext | None = None


def register_sse_context(app: Application, context: SSEContext) -> None:
    global _DEFAULT_CONTEXT
    app["sse_context"] = context
    _DEFAULT_CONTEXT = context


def get_sse_context(app: Application | None = None) -> SSEContext:
    if app is None:
        if _DEFAULT_CONTEXT is None:
            raise RuntimeError("SSE context is not initialized")
        return _DEFAULT_CONTEXT

    context = app.get("sse_context")
    if context is None:
        raise RuntimeError("SSE context is not initialized")
    return context


async def sse_broadcast(message: Any, *, ensure_meta: bool = True, app: Application | None = None) -> str | None:
    ctx = get_sse_context(app)
    return await ctx.broadcast(message, ensure_meta=ensure_meta)


async def sse_log(
    message: Any,
    level: str = "info",
    name: str | None = None,
    app: Application | None = None,
) -> str:
    ctx = get_sse_context(app)
    return await ctx.log(
        message,
        level=level,
        name=name,
    )

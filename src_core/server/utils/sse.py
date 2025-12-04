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



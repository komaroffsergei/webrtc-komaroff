from __future__ import annotations

import logging
from uuid import uuid4

import aiohttp
from aiohttp import web

from src_core.settings import API_URL, STACK_SERVICE_NAME
from src_core.utils.event_bus import event_log

logger = logging.getLogger("handle_init_map")


async def init_map_handler(request: web.Request) -> web.Response:
    """
    Publishes initial map state (airports + current position) via NATS.

    The frontend renders only what it receives via NATS events. This endpoint is
    a lightweight trigger so the server can publish that state after the client
    is ready and subscribed to events.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_URL}/airports/list") as resp:
                resp.raise_for_status()
                airports = (await resp.json()).get("results", [])

            async with session.get(f"{API_URL}/pilot/location") as resp:
                resp.raise_for_status()
                pos = await resp.json()

        airports_key = f"{STACK_SERVICE_NAME}.init.airports.{uuid4()}"
        airports_artifact = {"data": {"airports": airports}}
        await event_log(
            "command",
            "client",
            {
                "command": "SET_AIRPORTS",
                "artifacts": {
                    "last": airports_key,
                    "all": [airports_key],
                    "payload": {airports_key: airports_artifact},
                },
            },
            app=request.app,
            service=STACK_SERVICE_NAME,
        )

        position_key = f"{STACK_SERVICE_NAME}.init.position.{uuid4()}"
        position_artifact = {"data": {"current_position": {"lat": pos.get("lat"), "lon": pos.get("lon")}}}
        await event_log(
            "command",
            "client",
            {
                "command": "SET_POSITION",
                "artifacts": {
                    "last": position_key,
                    "all": [position_key],
                    "payload": {position_key: position_artifact},
                },
            },
            app=request.app,
            service=STACK_SERVICE_NAME,
        )

        return web.json_response({"status": "ok"})

    except Exception as exc:
        logger.exception("Failed to publish init map events")
        return web.json_response(
            {"error": "init_map_failed", "message": str(exc)},
            status=500,
        )


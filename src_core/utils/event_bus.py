from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping

from aiohttp.web_app import Application

logger = logging.getLogger("event_bus")


class EventBus:
    def __init__(self) -> None:
        self._subject: str | None = None
        self._service_name: str | None = None
        self._nats = None

    def configure(self, *, nats_client, subject: str, service_name: str) -> None:
        self._nats = nats_client
        self._subject = subject
        self._service_name = service_name
        logger.info("Event bus configured for subject %s", subject)

    async def publish(self, payload: Mapping[str, Any]) -> None:
        if not self._nats or not self._subject:
            raise RuntimeError("Event bus is not configured")
        await self._nats.publish(
            self._subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    async def log(
        self,
        message: Any,
        *,
        level: str = "info",
        name: str | None = None,
        event_name: str | None = None,
        service: str | None = None,
    ) -> str:
        payload = {
            "time": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "service": service or self._service_name,
            "name": event_name or name or "",
            "message": message,
            "uid": str(uuid.uuid4()),
        }

        await self.publish(payload)
        return payload["uid"]


_DEFAULT_BUS: EventBus | None = None


def register_event_bus(
    app: Application, *, nats_client, subject: str, service_name: str
) -> None:
    global _DEFAULT_BUS
    bus = EventBus()
    bus.configure(
        nats_client=nats_client,
        subject=subject,
        service_name=service_name,
    )
    app["event_bus"] = bus
    _DEFAULT_BUS = bus


def get_event_bus(app: Application | None = None) -> EventBus:
    if app is not None:
        bus = app.get("event_bus")
        if bus:
            return bus
    if _DEFAULT_BUS is None:
        raise RuntimeError("Event bus is not initialized")
    return _DEFAULT_BUS


async def event_log(
    message: Any,
    *,
    name: str | None = None,
    app: Application | None = None,
    service: str | None = None,
) -> str:
    bus = get_event_bus(app)
    return await bus.log(message, service=service, name=name)

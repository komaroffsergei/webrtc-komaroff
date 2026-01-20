from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp.web_app import Application

from src_core.utils.nats_logger import NatsLogger

logger = logging.getLogger("event_bus")

class EventBus:
    def __init__(self) -> None:
        self._subject: str | None = None
        self._service_name: str | None = None
        self._nats = None
        self._logger: NatsLogger | None = None

    def configure(self, *, nats_client, subject: str, service_name: str) -> None:
        self._nats = nats_client
        self._subject = subject
        self._service_name = service_name
        self._logger = NatsLogger(nats_client, subject, service_name)
        logger.info("Event bus configured for subject %s", subject)

    async def publish(self, payload: dict[str, Any]) -> None:
        if not self._nats or not self._subject:
            raise RuntimeError("Event bus is not configured")
        await self._nats.publish(
            self._subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    async def log(
        self,
        type: str,
        kind: str,
        data: dict[str, Any],
        *,
        name: str = "",
        service: str | None = None,
    ) -> str:
        if not self._logger:
            raise RuntimeError("Event bus is not configured")
        return await self._logger.log(type, kind, data, name=name, service=service)


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
    type: str,
    kind: str,
    data: dict[str, Any],
    *,
    name="",
    app: Application | None = None,
    service: str | None = None,
) -> str:
    bus = get_event_bus(app)
    return await bus.log(type, kind, data, service=service, name=name)

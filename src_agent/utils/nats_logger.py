from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

import logging
from nats.aio.client import Client as NatsClient



class NatsLogger:
    def __init__(self, nc: NatsClient, subject: str, service_name: str) -> None:
        self._nc = nc
        self._subject = subject
        self._service_name = service_name

    async def log(
        self,
        type: str,
        kind: str,
        data: dict[str, Any],
        *,
        name: str | None = None,
    ) -> str:
        payload = {
            "time": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "service": self._service_name,
            "type": type,
            "kind": kind,
            "data": data,
            "name": name or "",
            "uid": str(uuid.uuid4()),
        }
        await self._nc.publish(self._subject, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        return payload["uid"]

    async def info(self, message: Any, *, name: str | None = None) -> None:
        data = {"text": message} if isinstance(message, str) else {"payload": message}
        await self.log("log", "info", data, name=name)

    async def error(self, message: Any, *, name: str | None = None) -> None:
        data = {"text": message} if isinstance(message, str) else {"payload": message}
        await self.log("log", "error", data, name=name)

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Protocol

EVENT_KINDS = Literal["message", "log", "error", "control"]


class NatsPublisher(Protocol):
    async def publish(self, subject: str, data: bytes) -> None: ...


class NatsLogger:
    def __init__(self, nc: NatsPublisher, subject: str, service_name: str) -> None:
        self._nc = nc
        self._subject = subject
        self._service_name = service_name

    async def log(
        self,
        message: Any,
        *,
        name: str = "",
        kind: EVENT_KINDS = "log",
        service: str | None = None,
    ) -> str:
        payload = {
            "time": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "service": service or self._service_name,
            "kind": kind,
            "name": name or "",
            "message": message,
            "uid": str(uuid.uuid4()),
        }
        await self._nc.publish(
            self._subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        return payload["uid"]

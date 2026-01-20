from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol


class NatsPublisher(Protocol):
    async def publish(self, subject: str, data: bytes) -> None: ...


class NatsLogger:
    def __init__(self, nc: NatsPublisher, subject: str, service_name: str) -> None:
        self._nc = nc
        self._subject = subject
        self._service_name = service_name

    async def log(
        self,
        type: str,
        kind: str,
        data: dict[str, Any],
        *,
        name: str = "",
        service: str | None = None,
    ) -> str:
        payload = {
            "time": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "service": service or self._service_name,
            "type": type,
            "kind": kind,
            "data": data,
            "name": name or "",
            "uid": str(uuid.uuid4()),
        }
        await self._nc.publish(
            self._subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )
        return payload["uid"]

    async def info(self, text: str, *, name: str = "", service: str | None = None) -> str:
        return await self.log(
            "log",
            "info",
            {"text": text},
            name=name,
            service=service,
        )

    async def error(self, text: str, *, name: str = "", service: str | None = None) -> str:
        return await self.log(
            "log",
            "error",
            {"text": text},
            name=name,
            service=service,
        )

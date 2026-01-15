from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from nats.aio.client import Client as NatsClient
from src_llm.utils.to_json_safe import to_json_safe


class NatsLogger:
    def __init__(self, nc: NatsClient, subject: str, service_name: str) -> None:
        self._nc = nc
        self._subject = subject
        self._service_name = service_name

    async def log(
        self,
        message: Any,
        *,
        level: str = "info",
        name: str | None = None,
        kind: str | None = None,
    ) -> None:
        payload = {
            "time": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
            "service": self._service_name,
            "type": level,
            "kind": kind or "",
            "message": to_json_safe(message),
            "name": name or "",
        }

        await self._nc.publish(
            self._subject,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )

    async def info(self, message: Any, *, name: str | None = None) -> None:
        await self.log(message, level="info", name=name)

    async def error(self, message: Any, *, name: str | None = None) -> None:
        await self.log(message, level="error", name=name)

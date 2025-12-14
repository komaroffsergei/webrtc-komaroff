import json
from typing import Any
from nats.aio.client import Client as NatsClient

from src_llm.utils.to_json_safe import to_json_safe


class NatsPublisher:
    def __init__(self, nc: NatsClient):
        self._nc = nc

    async def publish(self, subject: str, payload: Any) -> None:
        safe = to_json_safe(payload)
        await self._nc.publish(
            subject,
            json.dumps(safe, ensure_ascii=False).encode("utf-8"),
        )

import json
import logging
from typing import Any

from nats.aio.client import Client as NATS

from src_agent.settings import (
    STACK_SERVICE_NAME,
    LLM_FRAMES_SUBJECT,
    AGENT_MAX_TOKENS, LLM_LOGS_SUBJECT, AGENT_LOGS_SUBJECT,
)

logger = logging.getLogger(STACK_SERVICE_NAME)


class LLMClient:
    """
    Классический RPC-клиент. Никаких HTTP.
    Работает строго через NATS.request().
    """

    def __init__(self, nc: NATS):
        self.nc = nc

    async def call(self, text: str) -> str:
        request = {
            "service": STACK_SERVICE_NAME,
            "text": text,
            "max_tokens": AGENT_MAX_TOKENS,
        }

        try:
            msg = await self.nc.request(
                LLM_FRAMES_SUBJECT,
                json.dumps(request, ensure_ascii=False).encode(),
            )
        except Exception as e:
            logger.error("Invalid JSON from L!!!!!LM: %s", e)
            return f"[LLM JSON decode !!!error: {e}]"

        try:
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            logger.error("Invalid JSON from LLM: %s", e)
            return f"[LLM JSON decode error: {e}]"

        # Вариант ответа LLM:
        # {"input": "...", "output": {"text": "..."}}
        out = payload.get("output") or {}
        return out.get("text", "")



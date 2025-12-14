import json
import logging
from typing import Any, Dict, List

from src_agent.settings import STACK_SERVICE_NAME

logger = logging.getLogger("agent.llm_client")


class LLMClient:
    def __init__(self, nc, llm_subject: str):
        self.nc = nc
        self.llm_subject = llm_subject

    async def call_llm_chat(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Отправка chat-запроса в LLM сервис.
        """

        request_payload = {
            "service": STACK_SERVICE_NAME,
            "messages": messages,
        }

        try:
            msg = await self.nc.request(
                self.llm_subject,
                json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
                timeout=120.0,
            )
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as e:
            logger.error("LLM chat request failed: %s", e)
            return {}

        return payload

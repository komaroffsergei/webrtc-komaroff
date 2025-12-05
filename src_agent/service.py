import json
import logging
import asyncio
from nats.aio.msg import Msg

from src_llm.utils.base_service import BaseService
from src_agent.settings import (
    STACK_SERVICE_NAME,
)
from src_agent.llm_client import LLMClient
from src_agent.mcp_agent import MCPAgent

logger = logging.getLogger(STACK_SERVICE_NAME)


class AgentService(BaseService):
    """
    Агент как NATS-микросервис.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.llm_client = None
        self.agent = None

    async def on_run(self):
        self.llm_client = LLMClient(self._nc)
        self.agent = MCPAgent(self.llm_client)
        await self._nats_logger.info(f"{STACK_SERVICE_NAME} ready")

    def on_message(self, msg: Msg) -> dict:
        """
        Entry point:
        src_core → NATS → сюда → MCPAgent.run()
        """

        try:
            payload = json.loads(msg.data.decode("utf-8"))
        except Exception as exc:
            return {"error": "invalid_json", "details": str(exc)}

        text = payload.get("text") or ""
        if not text:
            return {"error": "empty_text"}

        # BaseService вызывает on_message в to_thread,
        # поэтому async → sync через asyncio.run()
        result = asyncio.run(self.agent.run(text))

        return {
            "agent": STACK_SERVICE_NAME,
            "result": result,
        }

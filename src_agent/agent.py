import json
import logging
from typing import Any, Dict, List

from llm_client import LLMClient
from mcp_client import MCPClient
from settings import AGENT_MAX_STEPS

logger = logging.getLogger("agent.core")


class MCPAgent:
    def __init__(self, nc, *, llm_subject: str, max_steps: int = AGENT_MAX_STEPS):
        self.nc = nc
        self.llm_client = LLMClient(nc, llm_subject=llm_subject)
        self.mcp_client = MCPClient()
        self.max_steps = max_steps

    async def run(self, user_text: str) -> Dict[str, Any]:
        """
        MCP-агент с полноценным tool round-trip.
        """

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_text}
        ]

        logger.info("MCPAgent started")

        for step in range(1, self.max_steps + 1):
            logger.info("Agent step %d", step)

            llm_response = await self.llm_client.call_llm_chat(messages)

            if not llm_response:
                return {
                    "status": "error",
                    "reason": "empty_llm_response",
                }

            # 1. Добавляем ответ ассистента в контекст
            assistant_msg = {
                "role": "assistant",
                "content": llm_response.get("content", ""),
            }

            tool_calls = llm_response.get("tool_calls")

            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls

            messages.append(assistant_msg)

            # 2. Если tool_calls нет — это финальный ответ
            if not tool_calls:
                logger.info("Final answer reached")
                return {
                    "status": "ok",
                    "result": assistant_msg["content"],
                    "steps": step,
                }

            # 3. Обрабатываем все вызовы инструментов
            for call in tool_calls:
                tool_name = call["function"]["name"]
                args = call["function"].get("arguments", {}) or {}

                logger.info(
                    "Calling tool %s with args %s",
                    tool_name,
                    json.dumps(args, ensure_ascii=False),
                )

                try:
                    tool_result = await self.mcp_client.call_tool(
                        tool_name,
                        args,
                    )
                except Exception as exc:
                    logger.exception("Tool %s failed", tool_name)
                    tool_result = {
                        "status": "error",
                        "reason": str(exc),
                    }

                # 4. Результат tool возвращаем в LLM
                messages.append({
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

        logger.warning("Max steps reached")

        return {
            "status": "error",
            "reason": "max_steps_exceeded",
            "partial_context": messages,
        }

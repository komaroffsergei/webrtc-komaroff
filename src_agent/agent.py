import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from llm_client import LLMClient
from mcp_client import MCPClient
from settings import AGENT_MAX_STEPS
from src_agent.repositories.events import log_event

logger = logging.getLogger("agent.core")


class MCPAgent:
    def __init__(self, nc, *, llm_subject: str, max_steps: int = AGENT_MAX_STEPS, db=None):
        self.current_intent_id = None
        self.nc = nc
        self.llm_client = LLMClient(nc, llm_subject=llm_subject)
        self.mcp_client = MCPClient()
        self.max_steps = max_steps
        self.db = db

    async def run(self, *, user_text: str, session_id: str) -> Dict[str, Any]:
        """
        MCP-агент с полноценным tool round-trip.
        """

        messages: List[Dict[str, Any]] = [
            {"role": "user", "content": user_text}
        ]

        logger.info("MCPAgent started")

        for step in range(1, self.max_steps + 1):
            logger.info("Agent step %d", step)
            await log_event(
                self.db,
                session_id=session_id,
                intent_id=self.current_intent_id,
                role="SYSTEM",
                event_type="MESSAGE",
                name="llm_request",
                input={
                    "messages": messages,
                    "step": step,
                },
                output=None,
            )

            llm_response = await self.llm_client.call_llm_chat(messages)

            await log_event(
                self.db,
                session_id=session_id,
                intent_id=self.current_intent_id,
                role="LLM",
                event_type="MESSAGE",
                name="llm_response",
                input=None,
                output=llm_response,
            )

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

                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=self.current_intent_id,
                    role="TOOL",
                    event_type="TOOL_CALL",
                    name=tool_name,
                    input=args,
                    output=None,
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
                await log_event(
                    self.db,
                    session_id=session_id,
                    intent_id=self.current_intent_id,
                    role="TOOL",
                    event_type="TOOL_RESULT",
                    name=tool_name,
                    input=None,
                    output=tool_result,
                )

                # Результат tool возвращаем в LLM
                messages.append({
                    "role": "tool",
                    "name": call["function"]["name"],
                    "date": datetime.now(tz=timezone.utc).isoformat(timespec="milliseconds"),
                    "content": json.dumps(tool_result, ensure_ascii=False),
                })

        logger.warning("Max steps reached")

        await log_event(
            self.db,
            session_id=session_id,
            intent_id=self.current_intent_id,
            role="LLM",
            event_type="FINAL",
            name=None,
            input=None,
            output={"text": assistant_msg["content"]},
        )


        return {
            "status": "error",
            "reason": "max_steps_exceeded",
            "partial_context": messages,
        }

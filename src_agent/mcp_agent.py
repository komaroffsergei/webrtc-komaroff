import json
import logging
from typing import Any

from src_agent.llm_client import LLMClient
from src_agent.mcp_client import call_mcp
from src_agent.settings import STACK_SERVICE_NAME

logger = logging.getLogger(STACK_SERVICE_NAME)


class MCPAgent:
    """
    Минимальная рабочая версия MCP-агента.
    Позже можно расширить цепочку reasoning → tools → refine.
    """

    def __init__(self, llm: LLMClient):
        self.llm = llm
        # self.mcp_tools = mcp_tools

    async def run(self, user_text: str) -> dict[str, Any]:
        """
        Основной цикл работы агента:
        1) вызвать LLM для плана (получить tool_calls)
        2) выполнить инструменты
        3) вызвать LLM повторно с результатами инструментов
        """

        # ----- Шаг 1: план -----
        plan_prompt = (
            "<|system|>\n"
            "Ты агент, который решает задачи с помощью инструментов.\n"
            "Формат ответа:\n"
            "{\n"
            '  "thought": "...",\n'
            '  "tool_calls": [\n'
            "    {\n"
            '      "tool": "<имя инструмента>",\n'
            '      "parameters": { ... }\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "<|end|>\n"
            "<|user|>\n"
            f"{user_text}\n"
            "<|end|>\n"
        )

        plan_raw = await self.llm.call(plan_prompt)

        try:
            plan = json.loads(plan_raw)
        except Exception:
            # fallback: LLM не вывел JSON
            return {"final": plan_raw}

        tool_calls = plan.get("tool_calls") or []
        tool_results = []

        # ----- Шаг 2: выполнение инструментов -----
        for call in tool_calls:
            name = call.get("tool")
            params = call.get("parameters") or {}

            result = await self._execute_tool(name, params)

            tool_results.append(
                {
                    "tool": name,
                    "input": params,
                    "output": result,
                }
            )

        # ----- Шаг 3: финальный ответ -----
        final_prompt = (
            "<|system|>\n"
            "Ты агент. На вход ниже получены результаты инструментов.\n"
            "Ответь пользователю итоговым сообщением.\n"
            "<|end|>\n"
            "<|user|>\n"
            f"Пользователь спросил: {user_text}\n\n"
            f"Результаты инструментов:\n{json.dumps(tool_results, ensure_ascii=False, indent=2)}\n"
            "<|end|>\n"
        )

        final_raw = await self.llm.call(final_prompt)

        return {
            "plan": plan,
            "tool_results": tool_results,
            "final": final_raw,
        }


    # def _make_next_prompt(self, user_text, last_thought, last_summary):
    #         """
    #         Новый промпт на основе предыдущего шага.
    #         """
    #         return f"""
    # Изначально пользовательский запрос: {user_text}
    # Последний результат инструмента: Результат инструмента: {json.dumps(last_summary, ensure_ascii=False)}
    # Сформируй следующий шаг агента или закончи если результат достигнут.
    #
    # """

    async def _execute_tool(self, name: str, params: dict) -> Any:
        """
        Правильный вызов инструментов через MCP Gateway,
        используя прежнюю систему call_mcp().
        """

        try:
            result = await call_mcp(name, params)

            # MCP возвращает:
            #   { "ok": True, "data": {...} }
            #   { "ok": False, "error": "..." }

            if not isinstance(result, dict):
                return {"error": "invalid_mcp_response", "raw": str(result)}

            if result.get("ok"):
                return result["data"]

            return {
                "error": "mcp_error",
                "details": result.get("error", "unknown")
            }

        except Exception as exc:
            return {
                "error": "mcp_exception",
                "details": str(exc),
            }
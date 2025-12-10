import json
import logging
from llm_client import LLMClient
from mcp_client import MCPClient
from settings import AGENT_MAX_STEPS

logger = logging.getLogger("agent.core")


class MCPAgent:
    def __init__(self, nc, *, llm_subject: str, max_steps: int = 10):
        self.nc = nc
        self.llm_client = LLMClient(nc, llm_subject=llm_subject)
        self.mcp_client = MCPClient()
        self.max_steps = max_steps

    async def run(self, user_text: str):
        """Пошаговый MCP-агент для обработки пользовательского запроса"""
        step_prompt = user_text
        last_summary = {}
        full_context = {}

        logger.info("MCPAgent.run started")

        for step in range(1, self.max_steps + 1):
            # Вызов LLM для определения следующего шага
            raw = await self.llm_client.call_llm(step_prompt)
            parsed = raw.get("parsed")

            if not parsed:
                return "Ошибка: LLM вернул невалидный JSON."

            thought = parsed.get("thought", "")
            final_result = parsed.get("final_result", "")
            tool_calls = parsed.get("tool_calls") or []

            logger.debug(f"[AGENT THOUGHT] {thought}")

            # Проверка на завершение
            if final_result:
                return final_result

            # Если нет инструментов и нет финального результата
            if not tool_calls:
                return "Ошибка: нет tool_calls и нет final_result."

            # Проверка, что вызывается ровно один инструмент
            if len(tool_calls) != 1:
                return "Ошибка: агент должен вызывать ровно один инструмент на шаг."

            # Выполнение вызова инструмента
            item = tool_calls[0]
            tool = item["call"]["tool"]
            params = item["call"]["parameters"]

            # Вызов MCP инструмента
            real_result = await self.mcp_client.call_tool(tool, params)
            full_context[tool] = real_result

            # Проверка результата
            if not real_result.get("ok") or "error" in real_result:
                error_msg = real_result.get("error", "Неизвестная ошибка")
                return f"Ошибка при выполнении инструмента {tool}: {error_msg}"

            # Подготовка к следующему шагу
            last_summary = self._summarize_tool_result(real_result)
            item["result"] = real_result

            # Проверка на ошибку в результате
            if last_summary is None:
                return f"Ошибка: инструмент ничего не вернул: {real_result}"

            # Формирование следующего промпта
            step_prompt = self._make_next_prompt(
                user_text=user_text,
                last_thought=thought,
                last_summary=last_summary
            )

        return "Ошибка: слишком много шагов выполнения."

    def _summarize_tool_result(self, result) -> str:
        """Преобразование результата инструмента в краткую строку для следующего шага"""
        try:
            # Попытка получить структурированный результат
            data = result.get("data")
            if hasattr(data, "structured_content") and data.structured_content:
                return json.dumps(data.structured_content, ensure_ascii=False)
            elif hasattr(data, "content") and data.content:
                return data.content[0].text
            else:
                return json.dumps(data, ensure_ascii=False)
        except Exception as e:
            return f"Ошибка получения данных: {e}"

    def _make_next_prompt(self, user_text, last_thought, last_summary):
        """Формирование промпта для следующего шага агента"""
        return f"""
Изначальный пользовательский запрос: {user_text}
Результат инструмента: {json.dumps(last_summary, ensure_ascii=False)}
Сформируй следующий шаг агента или заверши работу, если результат достигнут.
Если предыдущий инструмент дал финальный ответ — заверши работу.
"""
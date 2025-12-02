import json
from .llm_client import call_llm
from .mcp_client import call_mcp
from .formatter import summarize_tool_result
from shared.sse import sse_log
from server.utils.sse import get_sse_context


class MCPAgent:
    def __init__(self, app, max_steps=10):
        self.app = app
        self.max_steps = max_steps

    async def run(self, user_text: str):
        """
        Запускает пошаговую MCP-цепочку.
        """
        step_prompt = user_text
        last_summary = None
        full_context = {}     # хранение реальных результатов инструментов

        ctx = get_sse_context(self.app)

        for step in range(1, self.max_steps + 1):
            raw = await call_llm(step_prompt)
            parsed = raw.get("parsed")

            if not parsed:
                return "Ошибка: LLM вернул невалидный JSON."

            thought = parsed["thought"]
            answer = parsed["answer"]
            tool_calls = parsed["tool_calls"]

            await sse_log(ctx, f"[AGENT THOUGHT] {thought}", level="debug")

            # FINISH
            if answer:
                return answer

            if not tool_calls:
                return "Ошибка: нет tool_calls и нет answer."

            # RUN TOOLS
            last_summary = {}
            for item in tool_calls:
                tool = item["call"]["tool"]
                params = item["call"]["parameters"]

                real_result = await call_mcp(tool, params)
                full_context[tool] = real_result

                summary = summarize_tool_result(tool, real_result)
                item["result"] = summary
                last_summary = summary

                await sse_log(ctx,
                              f"[TOOL] {tool} → {summary}",
                              level="info")

            # NEXT PROMPT
            step_prompt = self._make_next_prompt(
                user_text=user_text,
                last_thought=thought,
                last_summary=last_summary
            )

        return "Ошибка: слишком много шагов."

    def _make_next_prompt(self, user_text, last_thought, last_summary):
        """
        Новый промпт — короткий, только мысль и summary.
        """
        return f"""
Ты являешься MCP-агентом.
Ответь строго JSON с полями thought, tool_calls[], answer.

Последняя мысль: {last_thought}
Краткий результат последнего инструмента: {json.dumps(last_summary, ensure_ascii=False)}

Пользовательский запрос: {user_text}

Продолжай.
"""

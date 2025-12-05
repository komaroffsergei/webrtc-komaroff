import json

from mcp.types import CallToolResult

from ..llm.llm_client import call_llm
from ..mcp.mcp_client import call_mcp
from .sse import sse_log


class MCPAgent:
    def __init__(self, app=None, max_steps=10):
        self.app = app
        self.max_steps = max_steps

    async def run(self, user_text: str):
        """
        Пошаговый MCP-агент.
        """
        step_prompt = user_text
        last_summary = {}     # хранит последнее summary, если модель его вернула
        full_context = {}     # реальные результаты MCP-инструментов

        await sse_log("MCPAgent.run)", level="info", app=self.app)

        for step in range(1, self.max_steps + 1):
            raw = await call_llm(step_prompt)
            parsed = raw.get("parsed")

            if not parsed:
                return "Ошибка: LLM вернул невалидный JSON."

            thought = parsed.get("thought", "")
            final_result = parsed.get("final_result", "")
            tool_calls = parsed.get("tool_calls") or []

            await sse_log(f"[AGENT THOUGHT] {thought}", level="debug", app=self.app)

            # финальное завершение
            if final_result:
                return final_result

            # если нет инструментов и нет финала
            if not tool_calls:
                return "Ошибка: нет tool_calls и нет final_result."

            # выполняем РОВНО один инструмент
            if len(tool_calls) != 1:
                return "Ошибка: агент должен вызывать ровно один инструмент на шаг."

            item = tool_calls[0]
            tool = item["call"]["tool"]
            params = item["call"]["parameters"]

            # вызов MCP инструмента
            real_result = await call_mcp(tool, params)
            full_context[tool] = real_result

            # модель получит это в следующем prompt
            last_summary = self._summarize_tool_result(real_result)
            item["result"] = real_result

            # if isinstance(real_result, CallToolResult):
            #     safe = {
            #         "status": real_result.status,
            #         "result": real_result.result,
            #         "error": real_result.error,
            #     }
            # else:
            #     safe = real_result
            #

            # выходим если инструмент ничего не вернул
            if last_summary is None or real_result.get("ok") is False:
                return f"Ошибка: инструмент ничего не вернул или вернул ошибку: {real_result}"


            # создаём следующий prompt для модели
            step_prompt = self._make_next_prompt(
                user_text=user_text,
                last_thought=thought,
                last_summary=last_summary
            )

        return "Ошибка: слишком много шагов."

    def _summarize_tool_result(self, result) -> str:
        """
        Преобразовать CallToolResult или dict в короткую строку
        для передачи модели.
        """
        try:
            if result.get('data').structured_content:
                res = result.get('data').structured_content
            else:
                res = result.get('data').content[0].text
        except Exception as e:
            res = f"Ошибка получения данных: {e}"
        # if isinstance(result, dict):
        #     # результат твоего call_mcp: {"ok":..., "data":...}
        #     ok = result.get("ok")
        #     data = result.get("data")
        #
        #     if isinstance(data, CallToolResult):
        #         return self._summarize_calltool(data)
        #
        #     return f"ok={ok}"
        #
        # if isinstance(result, CallToolResult):
        #     return self._summarize_calltool(result)

        # fallback
        return res

    # def _summarize_calltool(self, ct: CallToolResult) -> str:
    #     """
    #     Сжать CallToolResult до 1 строки.
    #     """
    #
    #     if ct.is_error:
    #         return f"ошибка инструмента: {ct.error or 'неизвестно'}"
    #
    #     # structured_content — JSON объект (если есть)
    #     sc = ct.structured_content
    #
    #     if isinstance(sc, dict):
    #         # Возьмём только ключевые поля
    #         keys = list(sc.keys())[:3]
    #         kv = ", ".join(f"{k}={sc[k]}" for k in keys)
    #         return f"результат инструмента: {kv}"
    #
    #     return "инструмент выполнен"
    #

    def _make_next_prompt(self, user_text, last_thought, last_summary):
        """
        Новый промпт на основе предыдущего шага.
        """
        return f"""
Изначально пользовательский запрос: {user_text}
Последний результат инструмента: Результат инструмента: {json.dumps(last_summary, ensure_ascii=False)}
Сформируй следующий шаг агента или закончи если результат достигнут.

"""

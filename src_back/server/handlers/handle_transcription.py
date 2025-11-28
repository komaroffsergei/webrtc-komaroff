from ..utils.sse import sse_log, logger
import aiohttp
import json


# ------------------------------
# Helper: вызвать LLM
# ------------------------------
async def call_llm(prompt: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:6007/generate",
            json={"prompt": prompt, "max_tokens": 200}
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data


# ------------------------------
# Helper: вызвать MCP
# ------------------------------
async def call_mcp(tool: str, params: dict):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "http://127.0.0.1:6006/invoke",
            json={"tool": tool, "params": params}
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["result"]


# ------------------------------
# Helper: понять, это tool-call?
# ------------------------------
def is_tool_call(text: str):
    try:
        obj = json.loads(text)
        return isinstance(obj, dict) and "tool" in obj and "params" in obj
    except:
        return False



# ------------------------------
# КЛЮЧЕВОЕ ИЗМЕНЕНИЕ: правильный промпт-шаблон для продолжения цепочки
# ------------------------------
CONTINUE_PROMPT = """Ты уже получил результат предыдущего инструмента.
Продолжай выполнение задачи строго по протоколу MCP.

ПРАВИЛА (повторяю ещё раз):
- Отвечай ТОЛЬКО одним JSON: {"tool": "...", "parameters": {...}} или {"answer": "финальный ответ"}
- Если для завершения задачи нужны ещё инструменты — вызывай их по одному
- Никогда не пиши рассуждения, планы или промежуточные ответы
- Финальный ответ выдавай ТОЛЬКО через {"answer": "..."}

Результат предыдущего вызова:
{result}

Пользовательский запрос (напоминание): {original_query}
Продолжай."""

# ------------------------------
# Основная логика MCP-агента
# ------------------------------
# ------------------------------
# Переписанная agent_logic — теперь гоняет модель до конца
# ------------------------------
async def agent_logic(app, user_text: str, max_steps: int = 12) -> str:
    """
    Полностью автономный MCP-агент с прозрачным мышлением.
    Работает с новым JSON-форматом: thought + tool_calls[] + answer
    """
    # Первый промпт — просто пользовательский запрос
    current_prompt = user_text
    history = []  # накапливаем полные шаги для контекста (очень помогает)

    for step in range(1, max_steps + 1):
        # ←←← 1. Вызов LLM
        raw_response = await call_llm(current_prompt)

        await sse_log(app, f"LLM raw (шаг {step}): {raw_response}", level="debug")

        # ←←← 2. Безопасный парсинг (принимает и строку, и dict)
        try:
            if isinstance(raw_response, dict):
                data = raw_response.get('parsed')
            else:
                data = json.loads(raw_response)
                data = data.get("parsed")
        except (json.JSONDecodeError, TypeError) as e:
            await sse_log(app, f"Ошибка парсинга JSON на шаге {step}: {e}", level="error")
            return "Ошибка: модель вернула невалидный JSON."

        # ←←← 3. Приводим к нашему формату (страховка)
        if not isinstance(data, dict) or "thought" not in data or "tool_calls" not in data:
            return "Ошибка: модель нарушила требуемый формат ответа."

        thought = data.get("thought", "Нет мысли.")
        answer = data.get("answer", "").strip()
        tool_calls = data.get("tool_calls", [])

        await sse_log(app, f"Мысль агента (шаг {step}): {thought}", level="info")

        # ←←← 4. Если есть финальный ответ — возвращаем его
        if answer:
            await sse_log(app, f"Финальный ответ: {answer}", level="success")
            return answer

        # ←←← 5. Если нет tool_calls — это ошибка (модель забыла что делать)
        if not tool_calls:
            await sse_log(app, "Агент завершил tool_calls, но не дал answer → принудительный error_report", level="warning")
            return "Ошибка: агент завершил шаги, но не дал финальный ответ."

        # ←←← 6. Выполняем все pending tool_calls
        results = []
        for idx, item in enumerate(tool_calls):
            call = item.get("call")
            if not call or item.get("result") is not None:
                continue  # уже выполнен или битый

            tool_name = call.get("tool")
            params = call.get("parameters", {})

            await sse_log(app, f"Вызов инструмента: {tool_name} (обоснование: {item.get('thought', 'нет')})", level="info")

            try:
                result = await call_mcp(tool_name, params)
                await sse_log(app, f"Результат {tool_name}: {result}", level="debug")
            except Exception as e:
                result = {"error": str(e)}
                await sse_log(app, f"Ошибка инструмента {tool_name}: {e}", level="error")

            # Записываем результат прямо в структуру (для следующего шага)
            item["result"] = result
            results.append(f"{tool_name} → {json.dumps(result, ensure_ascii=False)}")

        # ←←← 7. Формируем следующий промпт
        history.append({
            "step": step,
            "thought": thought,
            "tools": tool_calls,
            "answer": answer
        })

        next_prompt = f"""Ты уже выполнил шаг {step}. Вот что произошло:

Последняя мысль: {thought}

Выполненные инструменты и их результаты:
{chr(10).join(f"- {r}" for r in results[-5:])}

Оригинальный запрос пользователя: {user_text}

Продолжай выполнение задачи. Отвечай строго в JSON-формате с thought, tool_calls[], answer."""

        # (Опционально) добавляем краткую историю последних 2 шагов — сильно помогает не терять контекст
        if len(history) >= 2:
            prev = history[-2]
            next_prompt += f"\n\nПредыдущий шаг (напоминание):\nМысль: {prev['thought']}\nИнструменты: {[c['call']['tool'] for c in prev['tools']]}"

        current_prompt = next_prompt

    # ←←← 8. Превышен лимит шагов
    await sse_log(app, "Превышено максимальное количество шагов", level="error")
    return "Ошибка: агент не смог завершить задачу за отведённое количество шагов."
# ------------------------------
# handle_transcription — теперь просто вызывает новый agent_logic
# ------------------------------
async def handle_transcription(app, data):
    try:
        text = "Найди аэропорт в радиусе 100 км."
        # text = data.get("text", "").strip()
        if not text:
            return

        await sse_log(app, f"Whisper: {text}", level="info")

        # ←←←←←←←←←←←←←←←←←←←←←←←←←←←
        # Теперь агент сам сделает ВСЕ шаги
        # ←←←←←←←←←←←←←←←←←←←←←←←←←←←
        final_answer = await agent_logic(app, text)

        await sse_log(app, f"MCP answer: {final_answer}", level="success")

    except Exception as e:
        logger.error(f"agent crash: {e}")
        await sse_log(app, f"Ошибка агента: {e}", level="error")
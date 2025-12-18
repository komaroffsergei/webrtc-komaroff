import json
import time

import ollama
from typing import List, Dict, Any

import src_llm_test.tools  # noqa: F401 (важно: регистрация тулзов)
from src_llm_test.db import DB_STORE, log_artifact, log_event, finish_session, finish_intent, create_session, \
    create_intent
from src_llm_test.settings import OLLAMA_URL, DEBUG
from src_llm_test.utils import normalize_tool_calls, log_step, log_final_answer, log_tool_call, \
    log_tool_result, normalize_args, log_user_query, log_system_prompt, log_llm_response, log_error, log_stats
from src_llm_test.mcp_tools import REGISTRY

TOOLS = [v["schema"] for v in REGISTRY.values()]
TOOL_IMPL = {k: v["fn"] for k, v in REGISTRY.items()}

MAX_STEPS = 10

SYSTEM_PROMPT = (
    "Ты — MCP агент\n"
    "Если требуется действие, ты ОБЯЗАН вызывать это действие ТОЛЬКО через tool_calls.\n"
    "Перед каждым действием пиши в content: РАССУЖДЕНИЕ: и кратко объясняй, что ты собираешься делать.\n"
    "Ограничения:\n"
    "НИКОГДА НЕ пиши текст в поле content при вызове инструментов.\n"
    "НИКОГДА НЕ описывай вызовы инструментов обычным текстом.\n"
    "НИКОГДА НЕ возвращай JSON в content, притворяясь вызовом инструмента.\n"
    "НИКОГДА НЕ выдумывай значения-заглушки.\n"
    "НИКОГДА НЕ выдумывай параметры.\n"
    "НИКОГДА НЕ запрашивать значения у пользователя.\n"
    "НИКОГДА НЕ повторяй тот же вызов с теми же аргументами после ошибки.\n"
    "ВСЕГДА СТРОГО соблюдай тип данных парамеров"
    "\n"
    "ПРАВИЛО ГЕОПОЗИЦИИ (ОБЯЗАТЕЛЬНО):\n"
    "Если запрос пользователя:\n"
    "- содержит слова: радиус, км, расстояние, ближайший, аэропорт\n"
    "- или требует географического расчёта\n"
    "ТО:"
    "- ТЫ ОБЯЗАН первым действием вызвать get_current_position\n"
    "- ЗАПРЕЩЕНО использовать любые координаты, полученные ранее\n"
    "- ЗАПРЕЩЕНО продолжать рассуждение без этого вызова\n"
    # "Требования к ответу\n"
    # "Всегда объясняй свои рассуждения в поле content текстом на русском языке"
    # "Не вызывай лишние инструменты если ответ получен"
    # "Правила локации:\n"
    # "- Если для задачи нужны координаты и они отсутствуют, ОБЯЗАТЕЛЬНО вызови get_current_position.\n"
    # "- Координаты (0,0) НЕДОПУСТИМЫ и не должны использоваться.\n"
    # "\n"
    # "Правила работы с инструментами:\n"
    # "- Используй аргументы инструментов СТРОГО в соответствии со схемой.\n"
    #
    # "- Если инструмент вернул ошибку, скорректируй следующий вызов.\n"
    #
    # "\n"
    # "Правила завершения:\n"
    # "- Верни финальный ответ обычным текстом на русском языке.\n"
    # "\n"
    # # "Правила агрегации:\n"
    # # "- НЕ забывай ранее полученные данные.\n"
    # "\n"
    # "Правила параметров:\n"
    #
    # "- Используй числовые параметры ТОЛЬКО если они явно указаны пользователем.\n"
    # "- Если числовое ограничение не задано пользователем, параметр должен быть опущен.\n"
)


def run_model(model: str, prompt: str, user_id):
    start_ts = time.perf_counter()

    session_id = create_session(user_id)
    intent_id = create_intent(
        session_id,
        user_id,
        intent_type="GENERIC_QUERY"
    )
    if DEBUG:
        log_user_query(prompt)
        log_system_prompt()

    client = ollama.Client(host=OLLAMA_URL, timeout=60)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    seq = 0
    steps = 0
    for step in range(1, MAX_STEPS + 1):
        steps += 1
        log_step(step)
        intent_id = create_intent(session_id, user_id, OLLAMA_URL)
        try:
            resp = client.chat(
                model=model,
                messages=messages,
                tools=TOOLS,
                options={"temperature": 0.0},
            )
        except Exception as e:
            log_error(e)

            log_event(
                session_id,
                intent_id,
                seq,
                role="SYSTEM",
                event_type="ERROR",
                name=model,
                input_data=None,
                output_data={"error": str(e)},
            )

            finish_intent(intent_id, "FAILED")
            finish_session(session_id, "FAILED")

            return {
                "model": model,
                "prompt": prompt,
                "steps": steps,
                "total_time_sec": round(time.perf_counter() - start_ts, 3),
                "status": "FAILED",
                "error": str(e),
            }

        msg = resp["message"]
        messages.append(msg)

        tool_calls = normalize_tool_calls(msg.get("tool_calls"))
        log_llm_response(msg.get("content"), tool_calls)

        if not tool_calls:
            log_final_answer(msg.get("content"))
            break

        for call in msg["tool_calls"]:
            name = call["function"]["name"]
            raw_args = call["function"]["arguments"]

            log_tool_call(name, raw_args)

            try:
                safe_args = normalize_args(TOOL_IMPL[name], raw_args)
                cont, result = TOOL_IMPL[name](**safe_args)
            except Exception as e:
                log_error(e)
                break

            log_tool_result(name, result)

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })

            if not cont:
                break

    total = time.perf_counter() - start_ts
    log_stats(steps, total)


MODELS = [
    "qwen3:0.6b",
    "qwen2.5:7b",
    "qwen3:1.7b",
    # "qwen3:8b",
]

QUERIES = [
    "Найди аэропорт в радиусе 250 км с самой короткой ВПП",
    "Найди ближайший открытый аэропорт",
    "Построй маршрут до ближайшего аэропорта",
]

if __name__ == "__main__":
    USER_ID = "user_demo_001"
    STATS = []

    for model in MODELS:
        for query in QUERIES:
            print(f"\nMODEL={model} QUERY={query}")
            stats = run_model(model, query, USER_ID)
            STATS.append(stats)

    print("\n=== RUN SUMMARY ===")
    for s in STATS:
        print(s)

    print("\n=== DB SNAPSHOT ===")
    print(json.dumps(DB_STORE, indent=2, ensure_ascii=False))

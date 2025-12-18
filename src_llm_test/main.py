import json

import ollama
from typing import List, Dict, Any

import src_llm_test.tools  # noqa: F401 (важно: регистрация тулзов)
from src_llm_test.settings import OLLAMA_URL
from src_llm_test.utils import normalize_tool_calls, log, log_step, log_model_decision, log_final_answer, log_tool_call, \
    log_tool_result, normalize_args
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



def run_model(model_name: str, user_prompt: str):
    client = ollama.Client(host=OLLAMA_URL, timeout=60.0)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    for step in range(1, MAX_STEPS + 1):
        log_step(step)

        response = client.chat(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            options={"temperature": 0.0},
        )

        message = response["message"]
        messages.append(message)

        tool_calls = normalize_tool_calls(message.get("tool_calls"))
        log_model_decision(message.get("content"), tool_calls)

        if not message.get("tool_calls"):
            log_final_answer(message.get("content"))
            return

        for call in message["tool_calls"]:
            name = call["function"]["name"]
            args = call["function"]["arguments"]

            log_tool_call(name, args)

            try:
                raw_args = call["function"]["arguments"]
                safe_args = normalize_args(TOOL_IMPL[name], raw_args)

                cont, result = TOOL_IMPL[name](**safe_args)
            except Exception as e:
                cont, result = False, {"status": "error", "message": str(e)}

            log_tool_result(name, result)

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })

            if not cont:
                break


MODELS = [
    # "qwen3:0.6b",
    "qwen3:1.7b",
    # "qwen2.5:7b",
    # "qwen3:8b",
]


if __name__ == "__main__":
    for model in MODELS:
        print(f"\n\n#################### MODEL: {model} ####################")
        run_model(
            model,
            "Найди аэропорт в радиусе 250 км с самой короткой ВПП",
        )

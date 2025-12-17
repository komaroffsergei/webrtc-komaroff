import ollama
import json
from typing import List, Dict, Any
import tools
from src_llm_test.settings import OLLAMA_URL
from src_llm_test.utils import normalize_tool_calls, log

# -----------------------------
# TOOLS SCHEMA
# -----------------------------
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "display_error",
            "description": str((
                "ИСПОЛЬЗУЙ ТОЛЬКО если произошла НЕВОССТАНАВЛИВАЯ ошибка "
                "и дальнейшие вызовы инструментов НЕВОЗМОЖНЫ. "
                "ЗАПРЕЩЕНО использовать при успешных или промежуточных результатах."
            )),
            "parameters": {
                "type": "object",
                "properties": {
                    "msg": {
                        "type": "string",
                        "description": "Подробное описание ошибки"
                    },
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_position",
            "description": str((
                "Получает текущую географическую позицию пользователя (широта и долгота).",
                "Вызывать всегда когда запрос имеет отношение к локации пользователя"
            )),
            "parameters": {
                "type": "object",
                "properties": {}
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "display_airports",
            "description": str((
                "Отображает аэропорты сохраненные в хранилище в результате работы другого инструмента",
            )),
            "parameters": {
                "type": "object",
                "properties": {}
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_airports",
            "description": str((
                "Ищет аэропорты в заданном радиусе от указанной географической точки",
                "Если после этого инструмента нужно показать пользователю список найденных аэропортов - вызови инструмент display_airports"
            )),
            "parameters": {
                "type": "object",
                "properties": {
                    "lat": {
                        "type": "number",
                        "description": "Широта точки поиска"
                    },
                    "lon": {
                        "type": "number",
                        "description": "Долгота точки поиска"
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Радиус поиска в километрах"
                    },
                },
                "required": ["lat", "lon", "radius_km"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_airport_by_name",
            "description": "Ищет аэропорт по полному или частичному названию",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Название или часть названия аэропорта"
                    }
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "runway_info",
            "description": "Возвращает информацию о взлётно-посадочных полосах аэропорта",
            "parameters": {
                "type": "object",
                "properties": {
                    "airport_id": {
                        "type": "string",
                        "description": "Идентификатор аэропорта"
                    }
                },
                "required": ["airport_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_airports",
            "description": (
                "Фильтрует и агрегирует ранее найденные аэропорты и их ВПП если об этом просил пользователь. "
                "Использует данные, сохранённые в артефактах. "
                "НЕ выполняет сетевые запросы."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "require_free_runway": {
                        "type": "boolean",
                        "description": (
                            "Если true — учитывать только аэропорты, "
                            "у которых есть хотя бы одна свободная ВПП"
                        )
                    },
                    "min_runway_length_m": {
                        "type": "number",
                        "minimum": 1,
                        "description": (
                            "НЕОБЯЗАТЕЛЬНЫЙ параметр. Минимальная длина свободной ВПП в метрах. "
                            "Использовать ТОЛЬКО если пользователь явно задал минимальную длину. "
                            "В противном случае параметр должен быть опущен."
                        )
                    },
                    "sort_by": {
                        "type": "string",
                        "enum": ["max_free_runway_length", "distance_km"],
                        "description": (
                            "Способ сортировки результатов: "
                            "по максимальной длине свободной ВПП "
                            "или по расстоянию"
                        )
                    },
                    "limit": {
                        "type": "number",
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Максимальное количество аэропортов в результате"
                    }
                },
                "optional": [
                    "require_free_runway",
                    "min_runway_length_m",
                    "limit"
                ],
            }
        }
    }
]

# -----------------------------
# TOOL IMPLEMENTATIONS
# -----------------------------

TOOL_IMPL = {
    "search_airports": tools.search_airports,
    "runway_info": tools.get_runway_info,
    "get_current_position": tools.get_current_position,
    "get_airport_by_name": tools.get_airport_by_name,
    "query_airports": tools.query_airports,
    "display_airports": tools.display_airports,
    "display_errors": tools.display_error,

}

# TOOL_FORMATTER_IMPL = {
#     "get_current_position_input_format": tools.get_current_position_input_format,
#     "search_airports_input_format": tools.search_airports_input_format,
# }

# -----------------------------
# CONFIG
# -----------------------------

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


# -----------------------------
# MCP LOOP
# -----------------------------

def run_model(model_name: str, user_prompt: str):
    instance = ollama.Client(
        host=OLLAMA_URL,
        timeout=60.0,
    )

    log(f"MODEL: {model_name}")
    log("GOAL", user_prompt)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    step = 0

    while True:
        step += 1
        if step > MAX_STEPS:
            log("ABORT", f"[{model_name}] exceeded MAX_STEPS={MAX_STEPS}")
            return

        log(f"STEP {step}")

        response = instance.chat(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            options={
                "temperature": 0.0,
                "top_p": 1.0,
                "top_k": 40,
            },
            think=False,
            stream=False,
        )

        message = response["message"]
        # log("THINKING", message.get("thinking"))

        messages.append(message)

        log("MODEL RESPONSE", {
            "content": message.get("content"),
            "thinking": message.get("thinking"),
            "tool_calls": normalize_tool_calls(message.get("tool_calls")),
        })

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            log("FINAL ANSWER", message.get("content"))
            tools.ARTIFACTS.clear()
            return

        for call in tool_calls:
            tool_name = call["function"]["name"]
            args = call["function"]["arguments"]

            log("TOOL CALL", {
                "name": tool_name,
                "arguments": args,
            })

            if tool_name not in TOOL_IMPL:
                cont = False
                result = {
                    "error": {
                        "type": "UNKNOWN_TOOL",
                        "message": f"Unknown tool {tool_name}"
                    }
                }
            else:
                try:
                    cont, result = TOOL_IMPL[tool_name](**args)
                except Exception as e:
                    msg = str(e)
                    cont = False
                    result = {
                            "error": {
                                "type": "TOOL_EXCEPTION",
                                "message": msg
                            }
                        }

            log("TOOL RESULT", result)

            # fatal → выходим с модели
            if isinstance(result, dict):
                err = result.get("error")
                if err and err.get("type") == "FATAL_TOOL_ERROR":
                    log("FATAL", f"[{model_name}] backend unavailable, skipping model")
                    tools.ARTIFACTS.clear()
                    return

            if cont is False:
                print(f"[{model_name}] FINISHED BY TOOL: {result}")
                tools.ARTIFACTS.clear()
                return
            else:
                msg = {
                    "role": "tool",
                    "tool_name": tool_name,
                    "content": result
                }
                log("NEW MSG FOR MODEl", msg)
                messages.append(msg)
                continue


# -----------------------------
# ENTRYPOINT
# -----------------------------

if __name__ == "__main__":
    MODELS = [
        "granite4:1b",
        # "qwen3-vl:4b",
        # "qwen3-vl:8b"
    ]

    USER_PROMPT = "Найди аэропорт в радиусе 150 км c самой короткой ВПП"

    for model in MODELS:
        run_model(model, USER_PROMPT)

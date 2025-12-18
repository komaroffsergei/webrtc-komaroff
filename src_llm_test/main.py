import json

import ollama
from typing import List, Dict, Any

import src_llm_test.tools  # noqa: F401 (важно: регистрация тулзов)
from src_llm_test.settings import OLLAMA_URL
from src_llm_test.utils import normalize_tool_calls, log
from src_llm_test.mcp_tools import REGISTRY

TOOLS = [v["schema"] for v in REGISTRY.values()]
TOOL_IMPL = {k: v["fn"] for k, v in REGISTRY.items()}

MAX_STEPS = 10

SYSTEM_PROMPT = "Ты MCP агент. Используй инструменты строго через tool_calls."


def run_model(model_name: str, user_prompt: str):
    client = ollama.Client(host=OLLAMA_URL, timeout=60.0)

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    for step in range(1, MAX_STEPS + 1):
        log(f"STEP {step}")

        response = client.chat(
            model=model_name,
            messages=messages,
            tools=TOOLS,
            options={"temperature": 0.0},
        )

        message = response["message"]
        messages.append(message)

        log("MODEL RESPONSE", {
            "content": message.get("content"),
            "tool_calls": normalize_tool_calls(message.get("tool_calls")),
        })

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            log("FINAL ANSWER", message.get("content"))
            return

        for call in tool_calls:
            name = call["function"]["name"]
            args = call["function"]["arguments"]

            log("TOOL CALL", {"name": name, "args": args})

            try:
                cont, result = TOOL_IMPL[name](**args)
            except Exception as e:
                cont, result = False, f"Ошибка инструмента: {e}"

            log("TOOL RESULT", result)

            messages.append({
                "role": "tool",
                "tool_name": name,
                "content": json.dumps(result, ensure_ascii=False),
            })

            if not cont:
                continue


if __name__ == "__main__":
    run_model(
        "qwen2.5:7b",
        "Найди аэропорт в радиусе 150 км с самой короткой ВПП",
    )

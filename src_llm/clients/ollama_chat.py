import json
from typing import Any


def chat(client, *, model: str, messages: list, tools: list, options: dict, think: bool) -> dict[str, Any]:
    response = client.chat(
        model=model,
        messages=messages,
        tools=tools or [],
        options=options or {},
        think=think,
        stream=False,
    )
    message = response.get("message", {})
    _normalize_tool_calls(message)
    return {
        "message": message,
        "model": response.get("model", model),
        "provider": "ollama",
    }


def _normalize_tool_calls(message: dict) -> None:
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        args = function.get("arguments")
        if isinstance(args, str):
            try:
                function["arguments"] = json.loads(args)
            except json.JSONDecodeError:
                function["arguments"] = {}

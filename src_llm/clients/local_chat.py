import json
import re
from typing import Any

TOOL_CALL_RE = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.S)


def chat(
    llama,
    *,
    model: str,
    messages: list,
    tools: list,
    options: dict,
    max_tokens: int,
) -> dict[str, Any]:
    params = {
        "temperature": options.get("temperature", 0.0),
        "top_p": options.get("top_p"),
        "top_k": options.get("top_k"),
        "max_tokens": options.get("num_predict") or options.get("max_tokens") or max_tokens,
    }
    params = {k: v for k, v in params.items() if v is not None}

    response = llama.create_chat_completion(
        messages=messages,
        tools=tools or [],
        **params,
    )
    choices = response.get("choices") or []
    message = choices[0].get("message", {}) if choices else {}
    tool_calls = _parse_tool_calls(message.get("content") or "")
    if tool_calls:
        message["tool_calls"] = tool_calls
    _normalize_tool_calls(message)
    return {
        "message": message,
        "model": model,
        "provider": "local",
    }


def _parse_tool_calls(content: str) -> list[dict]:
    calls = []
    for raw in TOOL_CALL_RE.findall(content):
        try:
            payload = json.loads(raw.strip())
        except json.JSONDecodeError:
            continue
        name = payload.get("name")
        if not name:
            continue
        calls.append({"function": {"name": name, "arguments": payload.get("arguments", {})}})
    return calls


def _normalize_tool_calls(message: dict) -> None:
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        args = function.get("arguments")
        if isinstance(args, str):
            try:
                function["arguments"] = json.loads(args)
            except json.JSONDecodeError:
                function["arguments"] = {}

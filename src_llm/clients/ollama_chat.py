import json
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

INVALID_JSON_RETRIES = 1
INVALID_JSON_RETRY_DELAY_S = 0.25


def chat(client, *, model: str, messages: list, tools: list, options: dict, think: bool) -> dict[str, Any]:
    payload = {
        "model": model,
        "messages": messages,
        "tools": tools or [],
        "options": options or {},
        "think": think,
        "stream": False,
    }
    response = _request_json(client, payload)
    message = response.get("message", {})
    _normalize_tool_calls(message)
    return {
        "message": message,
        "model": response.get("model", model),
        "provider": "ollama",
    }


def _request_json(client, payload: dict[str, Any]) -> dict[str, Any]:
    last_error: json.JSONDecodeError | None = None

    for attempt in range(INVALID_JSON_RETRIES + 1):
        response = client._request_raw("POST", "/api/chat", json=payload)
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            last_error = exc
            preview = response.text[:300].replace("\n", "\\n")
            logger.warning(
                "ollama returned invalid JSON attempt=%s content_length=%s preview=%r",
                attempt + 1,
                len(response.content),
                preview,
            )
            if attempt < INVALID_JSON_RETRIES:
                time.sleep(INVALID_JSON_RETRY_DELAY_S * (attempt + 1))
                continue
            break

        if isinstance(data, dict):
            return data
        raise ValueError("Ollama response must be a JSON object")

    raise ValueError("Ollama returned invalid JSON response") from last_error


def _normalize_tool_calls(message: dict) -> None:
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        args = function.get("arguments")
        if isinstance(args, str):
            try:
                function["arguments"] = json.loads(args)
            except json.JSONDecodeError:
                function["arguments"] = {}

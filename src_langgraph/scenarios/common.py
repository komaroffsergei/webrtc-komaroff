from __future__ import annotations

from typing import Any

from src_shared.contracts import LlmResponse


def extract_llm_text(resp: LlmResponse) -> str | None:
    """Возвращает `response_text` из LLM-ответа, если он валиден и непустой."""
    if not resp.ok or not isinstance(resp.data, dict):
        return None
    value = resp.data.get("response_text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def normalize_tool_params(resp: LlmResponse) -> dict[str, Any]:
    """Нормализует ответ mode=tool_params к структуре extracted/missing/prompt."""
    if not resp.ok or not isinstance(resp.data, dict):
        return {"extracted": {}, "missing": [], "prompt": None}

    data = dict(resp.data)
    extracted = data.get("extracted") if isinstance(data.get("extracted"), dict) else {}
    missing = data.get("missing") if isinstance(data.get("missing"), list) else []
    prompt = data.get("prompt")
    if prompt is not None and not isinstance(prompt, str):
        prompt = str(prompt)
    return {"extracted": extracted, "missing": [str(x) for x in missing], "prompt": prompt}


def merge_non_empty_params(base: dict[str, Any], new_values: dict[str, Any]) -> dict[str, Any]:
    """Мержит словари параметров, игнорируя None и пустые строки."""
    merged = dict(base or {})
    for key, value in (new_values or {}).items():
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        merged[key] = value
    return merged


def extract_nested_data(payload: Any) -> dict[str, Any] | None:
    """Извлекает вложенный объект `data` из tool-пейлоада."""
    if not isinstance(payload, dict):
        return None
    inner = payload.get("data")
    return inner if isinstance(inner, dict) else None

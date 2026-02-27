from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parent / "config" / "scenarios"


@lru_cache(maxsize=32)
def load_config(name: str) -> dict[str, Any]:
    """Загружает и кеширует JSON-конфиг сценария по имени файла."""
    path = CONFIG_DIR / f"{name}.json"
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise RuntimeError(f"Invalid config shape in {path}")
    return raw


def text_block(value: Any, default: str) -> str:
    """Нормализует текст: принимает строку или список строк, иначе возвращает default."""
    if isinstance(value, str):
        text = value.strip()
        return text if text else default
    if isinstance(value, list):
        lines = [str(item).strip() for item in value if str(item).strip()]
        if lines:
            return "\n".join(lines)
    return default


def dict_value(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    """Возвращает словарь-копию либо безопасный словарь по умолчанию."""
    if isinstance(value, dict):
        return dict(value)
    return dict(default or {})


def list_of_dicts(value: Any, default: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    """Возвращает список словарей, отфильтровывая все значения другого типа."""
    if not isinstance(value, list):
        return list(default or [])
    out: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            out.append(dict(item))
    return out if out else list(default or [])

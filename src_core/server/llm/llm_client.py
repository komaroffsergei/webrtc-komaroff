import json
import os
import logging

from src_core.server.utils.extract_json_from_text import extract_json_from_text
from src_core.server.settings import (
    NATS_URL,
    NATS_FRAMES_SUBJECT,
    STACK_SERVICE_NAME,
)
from src_core.server.utils.nats_client import NatsClient

logger = logging.getLogger("llm_client")

# HTTP-эндпоинт оставляем как запасной вариант
LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:6007/generate")

_NATS_CLIENT: NatsClient | None = None


async def _get_nats_client() -> NatsClient:
    global _NATS_CLIENT
    if _NATS_CLIENT is None:
        client = NatsClient(NATS_URL)
        await client.connect()
        _NATS_CLIENT = client
    return _NATS_CLIENT


async def _call_llm_via_nats(text: str) -> dict:
    client = await _get_nats_client()

    request_payload = {
        "service": STACK_SERVICE_NAME,
        "text": text,
        # при желании сюда можно прокинуть max_tokens
    }

    msg = await client.request(
        NATS_FRAMES_SUBJECT,
        json.dumps(request_payload, ensure_ascii=False).encode("utf-8"),
        timeout=60.0,
    )

    try:
        payload = json.loads(msg.data.decode("utf-8"))
    except Exception as e:
        logger.error("Invalid JSON response from LLM via NATS: %s", e)
        return {"raw": f"LLM NATS response decode error: {e}", "parsed": None}

    # Унификация формата:
    # 1) прямой ответ { "text": "..." }
    # 2) обёртка BaseService: { "input": "...", "output": { "text": "..." }, "time": ... }
    raw = None
    if isinstance(payload, dict):
        if "text" in payload:
            raw = payload.get("text")
        elif isinstance(payload.get("output"), dict) and "text" in payload["output"]:
            raw = payload["output"]["text"]

    if raw is None:
        # fallback: вывалить весь payload строкой
        raw = json.dumps(payload, ensure_ascii=False)

    parsed = None
    try:
        parsed = extract_json_from_text(raw)
    except Exception as e:
        logger.error("Failed to parse JSON from LLM text: %s", e)
        parsed = None

    return {
        "raw": raw,
        "parsed": parsed,
    }


async def _call_llm_via_http(text: str) -> dict:
    # старый код оставляем как резерв — на случай, если NATS/LLM-сервис не поднят
    try:
        import httpx  # локальный импорт, чтобы не дёргать зависимость, если не используется
    except ImportError as e:
        logger.error("httpx is not installed, HTTP fallback unavailable: %s", e)
        return {"raw": f"LLM HTTP client missing dependency: {e}", "parsed": None}

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(LLM_URL, json={"text": text})
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        logger.error("LLM HTTP request failed: %s", e)
        return {"raw": f"LLM HTTP error: {e}", "parsed": None}

    raw = payload.get("text", "")

    parsed = None
    try:
        parsed = extract_json_from_text(raw)
    except Exception as e:
        logger.error("Failed to parse JSON from LLM HTTP text: %s", e)
        parsed = None

    return {
        "raw": raw,
        "parsed": parsed,
    }


async def call_llm(text: str) -> dict:
    """
    Универсальный клиент к LLM-сервису (src_llm).

    Ожидает от сервиса текст, старается выдернуть JSON
    и вернуться в виде:
        { "raw": "<сырой ответ>", "parsed": <dict | None> }
    """
    try:
        return await _call_llm_via_nats(text)
    except Exception as e:
        logger.error("LLM NATS call failed, fallback to HTTP: %s", e)

    return await _call_llm_via_http(text)

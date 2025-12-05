import json
import os

import httpx
import logging

from src_core.server.utils.extract_json_from_text import extract_json_from_text

logger = logging.getLogger("llm_client")

LLM_URL = os.getenv("LLM_URL", "http://127.0.0.1:6007/generate")


async def call_llm(text: str) -> dict:
    """
    Универсальный клиент к LLM-сервису (src_llm).

    Ожидает ответ вида:
        { "text": "<raw model text>" }

    И возвращает:
        {
            "raw": "...",
            "parsed": <dict | None>
        }

    Если parsed не получается — parsed = None.
    """
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(LLM_URL, json={"text": text})
            r.raise_for_status()
            payload = r.json()
    except Exception as e:
        logger.error("LLM request failed: %s", e)
        return {"raw": f"LLM error: {e}", "parsed": None}

    raw = payload.get("text", "")
    parsed = None

    # parse JSON from model output
    if raw:
        try:
            parsed = extract_json_from_text(raw)
        except Exception as e:
            parsed = None
            logger.error("LLM request failed: %s", e)
            return {"raw": f"LLM error: {e}", "parsed": None}


    return {
        "raw": raw,
        "parsed": parsed
    }

from asyncio import run_coroutine_threadsafe
from pathlib import Path

from fastapi import FastAPI, Body
import httpx
import logging
import os

from utils.nats_logger import NatsLogger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_llm")

app = FastAPI()

# адрес LLM-бэкенда
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "osmosis-mcp-4bQ8_0")

# Ограничения
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "8192"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "2048"))

SSE_SERVICE_NAME = os.getenv("LLM_SERVICE_NAME", "src_mcp_llm")

# системный промпт можно задавать ENV-ом, но если пусто — грузим из файла
SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")
SYSTEM_PROMPT = Path(SYSTEM_PROMPT_FILE).read_text(encoding="utf-8").strip()

NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")


@app.post("/generate")
async def generate(payload: dict = Body(...)):
    text = (payload.get("text") or "").strip()
    max_tokens = (payload.get("max_tokens") or MAX_OUTPUT_TOKENS)
    prompt = (
        f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
        f"<|user|>\n{text}\n<|end|>\n"
    )

    req = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "num_predict": max_tokens,
        "stream": False
    }

    async with httpx.AsyncClient(timeout=120) as client:
        r = await client.post(f"{OLLAMA_URL}/api/generate", json=req)
        r.raise_for_status()
        data = r.json()
        result = data.get("response")

        logger.info(result, name="llm.response")
        return {"text": result}
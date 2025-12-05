# from asyncio import run_coroutine_threadsafe
# from pathlib import Path
#
# from fastapi import FastAPI, Body
# import httpx
# import logging
# import os
#
# from utils.nats_logger import NatsLogger
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger("mcp_llm")
#
# app = FastAPI()
#
# # адрес LLM-бэкенда
# OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
# OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "osmosis-mcp-4bQ8_0")
#
# # Ограничения
# MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "8192"))
# DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "2048"))
#
# SSE_SERVICE_NAME = os.getenv("LLM_SERVICE_NAME", "src_llm")
#
# # системный промпт можно задавать ENV-ом, но если пусто — грузим из файла
# SYSTEM_PROMPT_FILE = os.getenv("SYSTEM_PROMPT_FILE", "system_prompt.txt")
# SYSTEM_PROMPT = Path(SYSTEM_PROMPT_FILE).read_text(encoding="utf-8").strip()
#
# NATS_LOGS_SUBJECT = os.getenv("NATS_LOGS_SUBJECT", "nats.logs")
#
#
# @app.post("/generate")
# async def generate(payload: dict = Body(...)):
#     text = (payload.get("text") or "").strip()
#     max_tokens = (payload.get("max_tokens") or MAX_OUTPUT_TOKENS)
#     prompt = (
#         f"<|system|>\n{SYSTEM_PROMPT}<|end|>\n"
#         f"<|user|>\n{text}\n<|end|>\n"
#     )
#
#     req = {
#         "model": OLLAMA_MODEL,
#         "prompt": prompt,
#         "num_predict": max_tokens,
#         "stream": False
#     }
#
#     async with httpx.AsyncClient(timeout=120) as client:
#         r = await client.post(f"{OLLAMA_URL}/api/generate", json=req)
#         r.raise_for_status()
#         data = r.json()
#         result = data.get("response")
#
#         logger.info(result, name="llm.response")
#         return {"text": result}




# import asyncio
# import os
#
# import uvicorn
# from dotenv import load_dotenv
#
# load_dotenv()
# LLM_HOST = os.getenv("LLM_HOST", "127.0.0.1")
# LLM_PORT = int(os.getenv("LLM_PORT", "6007"))
#
# config = uvicorn.Config(
#     "main:app",
#     host=LLM_HOST,
#     port=LLM_PORT,
#     reload=False,
# )
#
# server = uvicorn.Server(config)
#
# if __name__ == "__main__":
#     asyncio.run(server.serve())


from __future__ import annotations

import asyncio
import logging


from settings import (
    NATS_FRAMES_SUBJECT,
    NATS_LOGS_SUBJECT,
    NATS_URL,
    STACK_SERVICE_NAME, OLLAMA_URL, OLLAMA_MODEL, SYSTEM_PROMPT_FILE, SYSTEM_PROMPT, MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TOKENS,
)
from service import LLMService



def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    service = LLMService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        frames_subject=NATS_FRAMES_SUBJECT,
        logs_subject=NATS_LOGS_SUBJECT,
        ollama_url=OLLAMA_URL,
        ollama_model=OLLAMA_MODEL,
        system_prompt_file=SYSTEM_PROMPT_FILE,
        system_prompt=SYSTEM_PROMPT,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        default_max_tokens=DEFAULT_MAX_TOKENS
    )
    await service.run()


def main() -> None:
    configure_logging()
    try:
        asyncio.run(_run_service())
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        logging.getLogger("main").exception("Service terminated with error: %s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()


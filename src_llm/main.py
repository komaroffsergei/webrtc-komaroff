from __future__ import annotations

import asyncio
import logging

from settings import (
    NATS_URL,
    STACK_SERVICE_NAME, OLLAMA_URL, SYSTEM_PROMPT_FILE, MAX_OUTPUT_TOKENS,
    DEFAULT_MAX_TOKENS, NATS_LLM_SUBJECT, USER_ID, NATS_EVENTS_SUBJECT, LLM_MODE,
    LLM_MODELS_DIR, OLLAMA_MODEL_FILE, LLM_CONTEXT_SIZE, LLM_CHAT_FORMAT,
    LLM_LOCAL_MODEL, LLM_REMOTE_MODEL,
)
from service import LLMService
from src_llm.settings import TOOLS_MANIFEST_FILE


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def _run_service() -> None:
    service = LLMService(
        service_name=STACK_SERVICE_NAME,
        nats_url=NATS_URL,
        llm_subject=f"{NATS_LLM_SUBJECT}{USER_ID}",
        events_subject=f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        ollama_url=OLLAMA_URL,
        llm_local_model=LLM_LOCAL_MODEL,
        llm_remote_model=LLM_REMOTE_MODEL,
        system_prompt_file=SYSTEM_PROMPT_FILE,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        default_max_tokens=DEFAULT_MAX_TOKENS,
        tools_manifest_file=TOOLS_MANIFEST_FILE,
        llm_mode=LLM_MODE,
        llm_models_dir=LLM_MODELS_DIR,
        ollama_model_file=OLLAMA_MODEL_FILE,
        llm_context_size=LLM_CONTEXT_SIZE,
        llm_chat_format=LLM_CHAT_FORMAT,
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

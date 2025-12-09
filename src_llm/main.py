from __future__ import annotations

import asyncio
import logging


from settings import (
    NATS_FRAMES_SUBJECT,
    NATS_LOGS_SUBJECT,
    NATS_URL,
    STACK_SERVICE_NAME, OLLAMA_URL, OLLAMA_MODEL, SYSTEM_PROMPT_FILE, MAX_OUTPUT_TOKENS,
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


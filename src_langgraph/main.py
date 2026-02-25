from __future__ import annotations

import asyncio
import logging
import os
import sys

from src_langgraph.service import LangGraphWorkflowService
from src_langgraph.settings import (
    MAX_CONCURRENCY,
    NATS_LANGGRAPH_HEALTH_SUBJECT,
    NATS_LANGGRAPH_RUN_SUBJECT,
    NATS_LLM_SUBJECT_PREFIX,
    NATS_REQUEST_TIMEOUT_SECONDS,
    NATS_TOOLS_PREFIX,
    NATS_URL,
    STACK_SERVICE_NAME,
    USER_ID,
)


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        level=log_level,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> None:
    configure_logging()
    logger = logging.getLogger(STACK_SERVICE_NAME)
    logger.info("Starting %s service...", STACK_SERVICE_NAME)

    svc = LangGraphWorkflowService(
        nats_url=NATS_URL,
        run_subject=NATS_LANGGRAPH_RUN_SUBJECT,
        health_subject=NATS_LANGGRAPH_HEALTH_SUBJECT,
        llm_subject_prefix=NATS_LLM_SUBJECT_PREFIX,
        tools_subject_prefix=NATS_TOOLS_PREFIX,
        user_id=USER_ID,
        request_timeout_s=NATS_REQUEST_TIMEOUT_SECONDS,
        max_concurrency=MAX_CONCURRENCY,
    )

    try:
        asyncio.run(svc.run())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as exc:
        logger.exception("Service terminated with error: %s", str(exc))
        sys.exit(1)


if __name__ == "__main__":
    main()


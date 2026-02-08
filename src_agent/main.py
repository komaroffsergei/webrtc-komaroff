"""
Entry point for `src_agent`.

`src_agent` is a thin runner: it accepts user text over NATS, loads runtime state from Postgres,
delegates scenario orchestration to n8n via `src_n8n` over NATS, persists updated runtime state,
and publishes UI commands/events over NATS.
"""

import asyncio
import logging
import os
import sys

from src_agent.service import AgentServer
from src_agent.settings import (
    DATABASE_URL,
    N8N_TIMEOUT_SECONDS,
    NATS_AGENT_SUBJECT,
    NATS_EVENTS_SUBJECT,
    NATS_N8N_RUN_SUBJECT,
    NATS_URL,
    RUNTIME_CONFLICT_RETRIES,
    STACK_SERVICE_NAME,
    USER_ID,
)


def configure_logging():
    """Configure service logging."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        level=log_level,
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main():
    """Service entrypoint."""
    configure_logging()
    logger = logging.getLogger(STACK_SERVICE_NAME)

    logger.info(f"Starting {STACK_SERVICE_NAME} service...")

    server = AgentServer(
        nats_url=NATS_URL,
        agent_subject=f"{NATS_AGENT_SUBJECT}{USER_ID}",
        events_subject=f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        n8n_subject=NATS_N8N_RUN_SUBJECT,
        n8n_timeout_s=N8N_TIMEOUT_SECONDS,
        db_url=DATABASE_URL,
        user_id=USER_ID,
        runtime_conflict_retries=RUNTIME_CONFLICT_RETRIES,
    )

    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        logger.info("Service stopped by user")
    except Exception as e:
        logger.exception(f"Service terminated with error: {e}")
        sys.exit(1)

    logger.info(f"{STACK_SERVICE_NAME} service stopped")


if __name__ == "__main__":
    main()

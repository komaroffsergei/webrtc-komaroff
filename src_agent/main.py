import asyncio
import logging
import os
import sys

from src_agent.service import AgentServer
from src_agent.settings import STACK_SERVICE_NAME, USER_ID, NATS_EVENTS_SUBJECT, AGENT_MAX_STEPS, NATS_AGENT_SUBJECT, \
    NATS_URL, NATS_LLM_SUBJECT, DATABASE_URL


def configure_logging():
    """Настройка логирования"""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        level=log_level,
        datefmt="%Y-%m-%d %H:%M:%S"
    )


def main():
    """Основная функция запуска сервиса"""
    configure_logging()
    logger = logging.getLogger(STACK_SERVICE_NAME)

    logger.info(f"Starting {STACK_SERVICE_NAME} service...")

    server = AgentServer(
        nats_url=NATS_URL,
        agent_subject=f"{NATS_AGENT_SUBJECT}{USER_ID}",
        llm_subject=f"{NATS_LLM_SUBJECT}{USER_ID}",
        events_subject=f"{NATS_EVENTS_SUBJECT}{USER_ID}",
        max_steps=AGENT_MAX_STEPS,
        db_url=DATABASE_URL,
        user_id=USER_ID,

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

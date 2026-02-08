import asyncio
import logging
import os
import sys

from src_n8n.service import N8nBridgeService
from src_n8n.settings import (
    DATABASE_URL,
    N8N_HTTP_TIMEOUT_SECONDS,
    N8N_WEBHOOK_BASE_URL,
    NATS_N8N_HEALTH_SUBJECT,
    NATS_N8N_RUN_SUBJECT,
    NATS_URL,
    STACK_SERVICE_NAME,
    TOOL_PROXY_HOST,
    TOOL_PROXY_PORT,
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

    svc = N8nBridgeService(
        nats_url=NATS_URL,
        database_url=DATABASE_URL,
        n8n_webhook_base_url=N8N_WEBHOOK_BASE_URL,
        n8n_http_timeout_s=N8N_HTTP_TIMEOUT_SECONDS,
        n8n_run_subject=NATS_N8N_RUN_SUBJECT,
        n8n_health_subject=NATS_N8N_HEALTH_SUBJECT,
        tool_proxy_host=TOOL_PROXY_HOST,
        tool_proxy_port=TOOL_PROXY_PORT,
        user_id=USER_ID,
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


import asyncio
import logging
import os
from service import AgentServer
from settings import STACK_SERVICE_NAME


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

    server = AgentServer()

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
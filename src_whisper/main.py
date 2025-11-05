#!/usr/bin/env python3
"""
Точка входа в минимальный сервис Whisper.
"""

import asyncio
import logging

from dotenv import load_dotenv

from config import ServiceConfig
from service import WhisperService


async def _run() -> None:
    load_dotenv()
    config = ServiceConfig.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    service = WhisperService(config)
    await service.run()


if __name__ == "__main__":
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass

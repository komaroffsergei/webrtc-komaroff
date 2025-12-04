import json
import asyncio
import logging
from nats.aio.client import Client as NATS

logger = logging.getLogger("shared_nats_logger")


class NATSLogger:
    def __init__(self, subject, url, service):
        self.subject = subject
        self.url = url
        self.nc: NATS | None = None
        self.lock = asyncio.Lock()
        self.service = service

    async def connect(self):
        if self.nc is None or self.nc.is_closed:
            self.nc = NATS()
            await self.nc.connect(self.url)
            logger.info(f"NATSLogger connected to {self.url}")

    async def publish(self, message: dict):
        async with self.lock:
            await self.connect()
            await self.nc.publish(self.subject, json.dumps(message).encode("utf-8"))

    async def info(self, msg: str, name: str = None):
        await self.publish({
            "service": self.service,
            "type": "info",
            "message": msg,
            "name": name
        })

    async def error(self, msg: str, name: str = None):
        await self.publish({
            "service": self.service,
            "type": "error",
            "message": msg,
            "name": name
        })

    async def answer(self, msg: str, name: str = None):
        await self.publish({
            "service": self.service,
            "type": "answer",
            "message": msg,
            "name": name
        })

# глобальный логгер, доступный всем сервисам
nats_logger = NATSLogger()

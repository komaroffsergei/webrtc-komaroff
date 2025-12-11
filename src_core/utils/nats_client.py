import nats
import logging

logger = logging.getLogger("NatsLogsClient")


class NatsClient:
    def __init__(self, url: str):
        self.url = url
        self.nc = None

    async def connect(self):
        """Connect to NATS and keep connection alive automatically."""
        self.nc = await nats.connect(
            servers=[self.url],
            max_reconnect_attempts=-1,   # infinite retries
            reconnect_time_wait=2,
            ping_interval=10,
        )
        logger.info(f"NATS logs client connected: {self.url}")
        return self.nc

    async def subscribe(self, subject: str, cb):
        """Subscribe to logs subject."""
        await self.nc.subscribe(subject, cb=cb)
        logger.info(f"NATS logs client subscribed: {subject}")


    async def request(self, subject, data, timeout=1):
        logger.info(f"NATS logs client request: {subject} `{data}`")
        return await self.nc.request(subject, data, timeout=timeout)

    async def publish(self, subject: str, data: bytes) -> None:
        logger.info("NATS publish: %s (%d bytes)", subject, len(data))
        await self.nc.publish(subject, data)

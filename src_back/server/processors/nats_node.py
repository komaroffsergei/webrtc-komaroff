import asyncio
import logging
import os
from typing import Optional

import nats
from av import AudioFrame

logger = logging.getLogger("audio.NatsNode")


from .base import ConsumerNode


class NatsNode(ConsumerNode):
    """
    NatsNode

    """

    def __init__(self, source_node) -> None:
        super().__init__(source_node)
        self.nc: Optional[nats.NATS] = None
        self.nc_url = os.getenv("NATS_URL", "nats://audio_nats:4222")
        self.subject = os.getenv("NATS_SUBJECT", "audio.frames")

    async def start(self) -> None:
        if self.nc is None:
            self.nc = await nats.connect(self.nc_url)
            logger.info(f"NATS connected: {self.nc_url}")
        await super().start()

    async def stop(self) -> None:
        await super().stop()
        if self.nc is not None:
            try:
                await self.nc.drain()
            except Exception:
                pass
            try:
                await self.nc.close()
            except Exception:
                pass
            self.nc = None

    async def handle_frame(self, frame: AudioFrame) -> None:
        print(
            f"NatsNode: frame pts={getattr(frame, 'pts', None)} sr={getattr(frame, 'sample_rate', None)} fmt={getattr(frame, 'format', None)}"
        )
        # Optional: publish lightweight ping or metadata instead of raw PCM to avoid heavy traffic
        # if self.nc is not None:
        #     meta = {
        #         "pts": getattr(frame, "pts", None),
        #         "sr": getattr(frame, "sample_rate", None),
        #         "fmt": str(getattr(frame, "format", None)),
        #         "samples": getattr(frame, "samples", None),
        #     }
        #     await self.nc.publish(self.subject, json.dumps(meta).encode("utf-8"))
        await self.fan_out(frame)

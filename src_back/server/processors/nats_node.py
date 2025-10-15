import asyncio
import json
import logging
import os
from typing import Optional

import nats
from av import AudioFrame

logger = logging.getLogger("audio.NatsNode")


from .base import ConsumerNode


class NatsNode(ConsumerNode):
    """
    Publishes audio frames to NATS JetStream and fans out downstream.
    Supports late source binding. Exposes ensure_js() to get JetStream context.
    """

    def __init__(self, source_node=None) -> None:
        super().__init__(source_node)
        self.nc: Optional[nats.NATS] = None
        self.js = None
        self.nc_url = os.getenv("NATS_URL", "nats://localhost:4222")
        self.subject = os.getenv("NATS_SUBJECT", "audio.frames")
        self.stream_name = os.getenv("NATS_STREAM", "audio-stream")

    async def ensure_js(self):
        if self.nc is None or not getattr(self.nc, "is_connected", False):
            self.nc = await nats.connect(self.nc_url)
            logger.info(f"NATS connected: {self.nc_url}")
        if self.js is None:
            self.js = self.nc.jetstream()
            # ensure stream exists
            try:
                await self.js.stream_info(self.stream_name)
            except Exception:
                await self.js.add_stream(name=self.stream_name, subjects=[self.subject])
                logger.info(f"JetStream stream ensured: {self.stream_name} -> {self.subject}")
        return self.js

    async def connect(self, nc_url: Optional[str] = None, subject: Optional[str] = None) -> None:
        if nc_url:
            self.nc_url = nc_url
        if subject:
            self.subject = subject
        await self.ensure_js()

    async def start(self) -> None:
        await self.ensure_js()
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
        # publish in bg
        # await self._publish_raw_frame(frame)
        asyncio.create_task(self._publish_raw_frame(frame))

        # continue
        await self.fan_out(frame)

    async def _publish_raw_frame(self, frame: AudioFrame) -> None:
        try:
            if self.js is None:
                await self.ensure_js()
            if len(frame.planes) == 0:
                logger.warning("Skipping empty audio frame")
                return

            # Encode full frame: [4b meta_len][meta_json][raw_bytes]
            raw_audio_bytes = bytes(frame.planes[0])

            # channels
            channels = 1
            if frame.layout and frame.layout.channels:
                try:
                    channels = len(frame.layout.channels)
                except Exception:
                    channels = 1

            meta = {
                "pts": frame.pts,
                "sample_rate": frame.sample_rate,
                "format": frame.format.name if frame.format else None,
                "samples": frame.samples,
                "channels": channels,
                "size_bytes": len(raw_audio_bytes),
            }

            meta_bytes = json.dumps(meta).encode("utf-8")
            payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes + raw_audio_bytes

            ack = await self.js.publish(self.subject, payload, timeout=5)
            logger.debug(f"Published raw frame (seq={ack.seq}, {len(payload)} bytes)")

        except Exception as e:
            logger.error(f"Failed to publish raw frame: {e}", exc_info=True)

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
    Publishes audio frames to NATS (core) and fans out downstream.
    JetStream support removed by requirement. ensure_js() now only ensures core NATS connection.
    """

    def __init__(self, source_node=None) -> None:
        super().__init__(source_node)
        self.nc: Optional[nats.NATS] = None
        self.nc_url = os.getenv("NATS_URL", "nats://localhost:4222")
        raw_subj = os.getenv("AUDIO_SUBJ") or os.getenv("NATS_SUBJECT") or "audio.frames"
        self.subject = raw_subj if not str(raw_subj).endswith(".") else f"{raw_subj}frames"

    async def ensure_nc(self):
        if self.nc is None or not getattr(self.nc, "is_connected", False):
            # Support multiple URLs in NATS_URL separated by comma
            urls = [u.strip() for u in str(self.nc_url).split(",") if u.strip()]
            self.nc = await nats.connect(
                servers=urls or [self.nc_url],
                max_reconnect_attempts=-1,
                reconnect_time_wait=2,
                ping_interval=10,
            )
            logger.info(f"NATS connected: {self.nc.connected_url.netloc}")
        # JetStream support removed: ensure only core NATS connection
        return self.nc

    def use_source(self, source) -> "NatsNode":
        """Bind upstream audio source after initialization and allow chaining."""
        self.bind_source(source)
        return self

    async def connect(self, nc_url: Optional[str] = None, subject: Optional[str] = None) -> None:
        if nc_url:
            self.nc_url = nc_url
        if subject:
            self.subject = subject
        await self.ensure_nc()

    async def start(self) -> None:
        await self.ensure_nc()
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
        # print(
        #     f"NatsNode: frame pts={getattr(frame, 'pts', None)} sr={getattr(frame, 'sample_rate', None)} fmt={getattr(frame, 'format', None)}"
        # )
        # publish in bg
        # await self._publish_raw_frame(frame)
        asyncio.create_task(self._publish_raw_frame(frame))

        # continue
        await self.fan_out(frame)

    async def _publish_raw_frame(self, frame: AudioFrame) -> None:
        try:
            await self.ensure_nc()
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

            await self.nc.publish(self.subject, payload)
            logger.info(f"Published raw frame via NATS, {len(payload)} bytes")

        except Exception as e:
            logger.error(f"Failed to publish raw frame: {e}", exc_info=True)

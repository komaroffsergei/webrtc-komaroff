import asyncio
import json
import logging
import uuid
from typing import Awaitable, Callable

import numpy as np
from av import AudioFrame
from nats.aio.msg import Msg

from .base import ConsumerNode

logger = logging.getLogger("audio.PhraseSegmenterNode")


class PhraseSegmenterNode(ConsumerNode):
    """
    Streams audio frames to the Whisper service and forwards transcriptions.
    """

    def __init__(
        self,
        app,
        source_node,
        nats_client,
        whisper_subject: str,
        on_transcription: Callable[[dict], Awaitable[None]],
        session_id: str | None = None,
        sample_rate: int = 16000,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        max_speech_duration_s: float = 30.0,
        speech_pad_ms: int = 30,
        threshold: float = 0.8,
        buffer_check_interval_s: float = 1.0,
        request_timeout: float = 30.0,
        max_pending_tasks: int = 3,
    ):
        super().__init__(source_node)

        self.app = app

        self.nc = nats_client
        self.whisper_subject = whisper_subject
        self.on_transcription = on_transcription
        self.session_id = session_id

        # Keep the original parameters for compatibility with existing callers,
        # but phrase segmentation now lives in the Whisper service.
        self.target_sample_rate = sample_rate
        self.request_timeout = request_timeout

        self._stream_id = str(uuid.uuid4())
        self._seq = 0
        self._reply_subject: str | None = None
        self._reply_subscription = None

        self._publish_tasks: set[asyncio.Task] = set()
        self._publish_semaphore = asyncio.Semaphore(max(1, max_pending_tasks))

    async def start(self) -> None:
        if not getattr(self.nc, "nc", None):
            raise RuntimeError("NATS client is not connected")

        self._reply_subject = self.nc.nc.new_inbox()
        self._reply_subscription = await self.nc.subscribe(self._reply_subject, cb=self._handle_whisper_message)
        logger.info(
            "Streaming audio to Whisper: subject=%s stream_id=%s reply=%s",
            self.whisper_subject,
            self._stream_id,
            self._reply_subject,
        )
        await super().start()

    async def stop(self) -> None:
        for task in list(self._publish_tasks):
            task.cancel()
        self._publish_tasks.clear()

        await self._publish_end()
        if self._reply_subscription is not None:
            try:
                await self._reply_subscription.unsubscribe()
            except Exception:
                logger.exception("Failed to unsubscribe from Whisper reply subject")
        self._reply_subscription = None
        self._reply_subject = None
        await super().stop()

    async def handle_frame(self, frame: AudioFrame) -> None:
        try:
            pcm = frame.to_ndarray()
            if pcm.ndim == 2:
                pcm = pcm.reshape(-1)

            sr = int(frame.sample_rate or self.target_sample_rate)
            int16_pcm = np.asarray(pcm, dtype="<i2")
            raw_bytes = int16_pcm.tobytes()

            self._seq += 1
            meta: dict[str, object] = {
                "type": "frame",
                "stream_id": self._stream_id,
                "seq": self._seq,
                "sample_rate": sr,
                "sample_width": 2,
                "channels": 1,
            }
            if self.session_id:
                meta["session_id"] = self.session_id

            meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
            payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes + raw_bytes

            if self._reply_subject:
                task = asyncio.create_task(self._publish(payload))
                self._publish_tasks.add(task)
                task.add_done_callback(self._publish_tasks.discard)

        except Exception as exc:
            logger.error("Error processing audio frame: %s", exc, exc_info=True)
        finally:
            await self.fan_out(frame)

    async def _publish(self, payload: bytes) -> None:
        if not self._reply_subject:
            return
        async with self._publish_semaphore:
            await self.nc.publish(self.whisper_subject, payload, reply=self._reply_subject)

    async def _publish_end(self) -> None:
        if not self._reply_subject:
            return
        try:
            self._seq += 1
            meta: dict[str, object] = {
                "type": "end",
                "stream_id": self._stream_id,
                "seq": self._seq,
                "sample_rate": int(self.target_sample_rate),
                "sample_width": 2,
                "channels": 1,
            }
            if self.session_id:
                meta["session_id"] = self.session_id
            meta_bytes = json.dumps(meta, ensure_ascii=False).encode("utf-8")
            payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes
            await self.nc.publish(self.whisper_subject, payload, reply=self._reply_subject)
        except Exception:
            logger.exception("Failed to publish stream end to Whisper")

    async def _handle_whisper_message(self, msg: Msg) -> None:
        try:
            data = json.loads(msg.data.decode("utf-8"))
        except Exception:
            logger.exception("Invalid JSON from Whisper")
            return

        if self.session_id:
            data.setdefault("session_id", self.session_id)
        try:
            await self.on_transcription(data)
        except Exception:
            logger.exception("Transcription handler failed")

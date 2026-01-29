from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

import numpy as np

from src_whisper.service import StreamState, WhisperService


class _DummyNc:
    def __init__(self) -> None:
        self.published: list[tuple[str, bytes]] = []

    async def publish(self, subject: str, payload: bytes) -> None:
        self.published.append((subject, payload))


class StreamSegmentationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.service = WhisperService(
            service_name="test",
            nats_url="nats://localhost:4222",
            asr_subject="nats.asr.test",
            logs_subject="nats.events.test",
            models_dir=Path("."),
            model_id="dummy",
        )
        self.service._nc = _DummyNc()  # type: ignore[assignment]

        # Replace transcription with a lightweight collector.
        self.segments: list[str] = []

        async def _fake_transcribe_and_publish(reply_subject, session_id, packet):
            self.segments.append(packet.phrase_id)

        self.service._transcribe_and_publish = _fake_transcribe_and_publish  # type: ignore[assignment]

    async def test_flush_on_trailing_silence(self) -> None:
        sr = 16000
        # 2 seconds buffer, last speech ends at 1.0s -> 1.0s trailing silence.
        audio = np.zeros((2 * sr,), dtype=np.float32)

        async def _fake_get_timestamps(_audio):
            return [{"start": 0, "end": sr}]

        self.service._get_timestamps = _fake_get_timestamps  # type: ignore[assignment]

        stream_id = "s1"
        self.service._streams[stream_id] = StreamState(
            reply_subject="inbox",
            session_id=None,
            buffer=[audio],
            buffer_sample_rate=sr,
            buffer_samples=int(audio.size),
        )

        await self.service._check_stream_buffer(stream_id, flush=False)
        await asyncio.gather(*list(self.service._tasks))

        self.assertEqual(len(self.segments), 1)
        # Stream stays open; only buffer is cleared on silence-based flush.
        self.assertIn(stream_id, self.service._streams)
        self.assertEqual(self.service._streams[stream_id].buffer, [])

    async def test_no_flush_without_enough_silence(self) -> None:
        sr = 16000
        audio = np.zeros((int(1.4 * sr),), dtype=np.float32)

        async def _fake_get_timestamps(_audio):
            # Last speech ends at 1.2s -> 0.2s silence (min_silence default is 0.5s).
            return [{"start": 0, "end": int(1.2 * sr)}]

        self.service._get_timestamps = _fake_get_timestamps  # type: ignore[assignment]

        stream_id = "s2"
        self.service._streams[stream_id] = StreamState(
            reply_subject="inbox",
            session_id=None,
            buffer=[audio],
            buffer_sample_rate=sr,
            buffer_samples=int(audio.size),
        )

        await self.service._check_stream_buffer(stream_id, flush=False)
        await asyncio.gather(*list(self.service._tasks))

        self.assertEqual(self.segments, [])
        self.assertIn(stream_id, self.service._streams)
        self.assertTrue(self.service._streams[stream_id].buffer)

    async def test_forced_flush_on_end(self) -> None:
        sr = 16000
        audio = np.zeros((sr,), dtype=np.float32)

        async def _fake_get_timestamps(_audio):
            return [{"start": 0, "end": sr}]

        self.service._get_timestamps = _fake_get_timestamps  # type: ignore[assignment]

        stream_id = "s3"
        self.service._streams[stream_id] = StreamState(
            reply_subject="inbox",
            session_id=None,
            buffer=[audio],
            buffer_sample_rate=sr,
            buffer_samples=int(audio.size),
        )

        await self.service._check_stream_buffer(stream_id, flush=True)
        await asyncio.gather(*list(self.service._tasks))

        self.assertEqual(len(self.segments), 1)
        self.assertNotIn(stream_id, self.service._streams)

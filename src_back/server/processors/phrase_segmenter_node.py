import asyncio
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, List

import numpy as np
import torch
from av import AudioFrame
from nats import NATS
from nats.errors import TimeoutError as NatsTimeoutError

from .base import ConsumerNode
from ..utils.audio_utils import resample_audio


logger = logging.getLogger("audio.PhraseSegmenterNode")


@dataclass
class PhraseSegment:
    audio: np.ndarray
    sample_rate: int
    start_time: float
    end_time: float
    duration: float
    phrase_id: str


class PhraseSegmenterNode(ConsumerNode):
    """
    Нода для обнаружения фраз, отправки их в Whisper и получения транскрипций.
    """

    def __init__(
        self,
        source_node,
        nats_client: NATS,
        whisper_subject: str,
        on_transcription: Callable[[dict], Awaitable[None]],
        sample_rate: int = 16000,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        max_speech_duration_s: float = 30.0,
        speech_pad_ms: int = 30,
        threshold: float = 0.8,
        buffer_check_interval_s: float = 1.0,
        request_timeout: float = 15.0,
        max_pending_tasks: int = 3,
    ):
        super().__init__(source_node)

        self.nc = nats_client
        self.whisper_subject = whisper_subject
        self.on_transcription = on_transcription

        self.target_sample_rate = sample_rate
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.max_speech_duration_s = max_speech_duration_s
        self.speech_pad_ms = speech_pad_ms
        self.threshold = threshold
        self.buffer_check_interval_s = buffer_check_interval_s
        self.request_timeout = request_timeout

        self.buffer: List[np.ndarray] = []
        self.buffer_sample_rate = sample_rate

        self.vad_model = None
        self.get_speech_timestamps = None

        self._check_in_progress = False
        self._pending_tasks: set[asyncio.Task] = set()
        self._pending_semaphore = asyncio.Semaphore(max_pending_tasks)

    async def start(self) -> None:
        await self._load_silero_vad()
        await super().start()

    async def stop(self) -> None:
        for task in list(self._pending_tasks):
            task.cancel()
        self._pending_tasks.clear()

        self.vad_model = None
        self.buffer.clear()
        await super().stop()

    async def handle_frame(self, frame: AudioFrame) -> None:
        try:
            if frame.sample_rate:
                self.buffer_sample_rate = frame.sample_rate

            pcm = frame.to_ndarray()
            if pcm.ndim == 2:
                pcm = pcm.reshape(-1)

            audio_float = pcm.astype(np.float32) / 32768.0
            self.buffer.append(audio_float)

            buffer_duration = sum(len(x) for x in self.buffer) / self.buffer_sample_rate

            if buffer_duration >= self.buffer_check_interval_s and not self._check_in_progress:
                asyncio.create_task(self._check_buffer_async())

        except Exception as exc:
            logger.error("Error processing audio frame: %s", exc, exc_info=True)
        finally:
            await self.fan_out(frame)

    async def _load_silero_vad(self) -> None:
        loop = asyncio.get_event_loop()

        def _load():
            model, utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            return model, utils[0]

        model, get_speech_timestamps = await loop.run_in_executor(None, _load)
        self.vad_model = model
        self.get_speech_timestamps = get_speech_timestamps
        logger.info("Silero VAD model loaded")

    async def _check_buffer_async(self) -> None:
        if self._check_in_progress:
            return

        self._check_in_progress = True
        try:
            await self._check_buffer()
        finally:
            self._check_in_progress = False

    async def _check_buffer(self) -> None:
        if not self.buffer or self.vad_model is None:
            return

        try:
            audio = np.concatenate(self.buffer)

            if self.buffer_sample_rate != self.target_sample_rate:
                audio = resample_audio(audio, self.buffer_sample_rate, self.target_sample_rate)

            if len(audio) / self.target_sample_rate < 1.0:
                return

            audio_tensor = torch.from_numpy(audio)

            loop = asyncio.get_event_loop()
            timestamps = await loop.run_in_executor(
                None,
                self._get_timestamps,
                audio_tensor,
            )

            if not timestamps:
                if len(audio) / self.target_sample_rate > 5.0:
                    self.buffer.clear()
                return

            last_segment = timestamps[-1]
            last_end_sample = last_segment["end"]
            silence_after = (len(audio) - last_end_sample) / self.target_sample_rate
            min_silence_s = self.min_silence_duration_ms / 1000.0

            if silence_after >= min_silence_s:
                for ts in timestamps:
                    start_sample = ts["start"]
                    end_sample = ts["end"]
                    segment_audio = audio[start_sample:end_sample]
                    duration = len(segment_audio) / self.target_sample_rate

                    phrase = PhraseSegment(
                        audio=segment_audio,
                        sample_rate=self.target_sample_rate,
                        start_time=start_sample / self.target_sample_rate,
                        end_time=end_sample / self.target_sample_rate,
                        duration=duration,
                        phrase_id=str(uuid.uuid4()),
                    )

                    task = asyncio.create_task(self._handle_phrase(phrase))
                    self._pending_tasks.add(task)
                    task.add_done_callback(self._pending_tasks.discard)

                self.buffer.clear()

        except Exception as exc:
            logger.error("Error checking buffer: %s", exc, exc_info=True)

    def _get_timestamps(self, audio_tensor):
        try:
            return self.get_speech_timestamps(
                audio_tensor,
                self.vad_model,
                sampling_rate=self.target_sample_rate,
                min_speech_duration_ms=self.min_speech_duration_ms,
                min_silence_duration_ms=self.min_silence_duration_ms,
                max_speech_duration_s=self.max_speech_duration_s,
                speech_pad_ms=self.speech_pad_ms,
                threshold=self.threshold,
                return_seconds=False,
            )
        except Exception as exc:
            logger.error("Error in VAD get_timestamps: %s", exc, exc_info=True)
            return []

    async def _handle_phrase(self, phrase: PhraseSegment) -> None:
        try:
            async with self._pending_semaphore:
                int16_audio = np.clip(phrase.audio, -1.0, 1.0)
                int16_audio = (int16_audio * 32767.0).astype(np.int16)
                raw_bytes = int16_audio.tobytes()

                meta = {
                    "type": "phrase",
                    "phrase_id": phrase.phrase_id,
                    "sample_rate": phrase.sample_rate,
                    "sample_width": 2,
                    "channels": 1,
                    "duration": phrase.duration,
                    "start_time": phrase.start_time,
                    "end_time": phrase.end_time,
                }

                meta_bytes = json.dumps(meta).encode("utf-8")
                payload = len(meta_bytes).to_bytes(4, "big") + meta_bytes + raw_bytes

                response = await self.nc.request(
                    self.whisper_subject,
                    payload,
                    timeout=self.request_timeout,
                )

                try:
                    data = json.loads(response.data.decode("utf-8"))
                except Exception as exc:
                    logger.error("Invalid response from whisper: %s", exc, exc_info=True)
                    return

                data.setdefault("phrase_id", phrase.phrase_id)
                await self.on_transcription(data)

        except NatsTimeoutError:
            logger.error("Whisper request timed out for phrase %s", phrase.phrase_id)
        except Exception as exc:
            logger.error("Failed to process phrase %s: %s", phrase.phrase_id, exc, exc_info=True)

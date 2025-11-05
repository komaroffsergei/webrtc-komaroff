#!/usr/bin/env python3
"""
Whisper Service - минимальный сервис транскрипции фраз, полученных через NATS.
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Optional, Tuple, List

import numpy as np
import nats
from dotenv import load_dotenv
from faster_whisper import WhisperModel

from config import ServiceConfig
from nats_log_handler import NatsLogHandler
from nats_logger import NatsLogger
from utils.audio_utils import resample_audio


load_dotenv()
logger = logging.getLogger("whisper.main")


class WhisperTranscriber:
    def __init__(
        self,
        model_path: str,
        device: str = "cpu",
        compute_type: str = "int8",
        language: str = "ru",
    ):
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.model: Optional[WhisperModel] = None

    async def load(self) -> None:
        loop = asyncio.get_event_loop()
        self.model = await loop.run_in_executor(None, self._load_model)
        logger.info("Whisper model loaded from %s", self.model_path)

    def _load_model(self) -> WhisperModel:
        return WhisperModel(
            self.model_path,
            device=self.device,
            compute_type=self.compute_type,
        )

    async def transcribe(self, audio: np.ndarray, sample_rate: int) -> Tuple[str, List[dict], float]:
        if self.model is None:
            raise RuntimeError("Whisper model is not loaded")

        loop = asyncio.get_event_loop()

        if sample_rate != 16000:
            audio = await loop.run_in_executor(
                None,
                resample_audio,
                audio,
                sample_rate,
                16000,
            )
            sample_rate = 16000

        start_time = time.time()
        segments = await loop.run_in_executor(None, self._run_model, audio)
        transcription_time = time.time() - start_time

        text = " ".join(seg["text"] for seg in segments).strip()
        return text, segments, transcription_time

    def _run_model(self, audio: np.ndarray) -> List[dict]:
        assert self.model is not None, "Model must be loaded before transcription"
        segments, _ = self.model.transcribe(
            audio,
            language=self.language,
            beam_size=5,
            without_timestamps=True,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        results = []
        for segment in segments:
            results.append(
                {
                    "text": segment.text.strip(),
                    "start": segment.start,
                    "end": segment.end,
                    "confidence": getattr(segment, "avg_logprob", 0.0),
                }
            )
        return results


class WhisperService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.nc: Optional[nats.NATS] = None
        self.transcriber = WhisperTranscriber(config.whisper.model_path)
        self.nats_logger: Optional[NatsLogger] = None

    async def run(self) -> None:
        await self._connect_nats()
        await self._setup_logging()
        await self.transcriber.load()

        subject = self.config.nats.whisper_subject
        await self.nc.subscribe(subject, cb=self._on_phrase)
        logger.info("Subscribed to phrases on %s", subject)

        while True:
            await asyncio.sleep(3600)

    async def _connect_nats(self) -> None:
        urls = [u.strip() for u in str(self.config.nats.url).split(",") if u.strip()]
        self.nc = await nats.connect(
            servers=urls or [self.config.nats.url],
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )
        logger.info("Connected to NATS: %s", self.nc.connected_url.netloc)

    async def _setup_logging(self) -> None:
        assert self.nc is not None
        whisper_logger = logging.getLogger("whisper")
        if not any(isinstance(handler, NatsLogHandler) for handler in whisper_logger.handlers):
            handler = NatsLogHandler(self.nc, self.config.nats.logs_subject, level=logging.DEBUG)
            handler.setFormatter(logging.Formatter("%(name)s: %(message)s"))
            whisper_logger.addHandler(handler)
            logger.info("NATS log handler attached")

        self.nats_logger = NatsLogger(
            self.nc,
            self.config.nats.logs_subject,
            service_name="whisper",
        )

    async def _on_phrase(self, msg):
        assert self.nc is not None
        phrase_id = None
        try:
            data = msg.data
            if len(data) < 4:
                raise ValueError("Payload too short")

            meta_len = int.from_bytes(data[:4], "big")
            if len(data) < 4 + meta_len:
                raise ValueError("Invalid metadata length")

            meta_raw = data[4 : 4 + meta_len]
            audio_bytes = data[4 + meta_len :]

            meta = json.loads(meta_raw.decode("utf-8")) if meta_raw else {}
            phrase_id = meta.get("phrase_id")
            sample_rate = int(meta.get("sample_rate", 16000))
            sample_width = int(meta.get("sample_width", 2))

            if sample_width == 2:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            elif sample_width == 4:
                audio_array = np.frombuffer(audio_bytes, dtype=np.int32).astype(np.float32) / 2147483648.0
            else:
                raise ValueError(f"Unsupported sample width: {sample_width}")

            if audio_array.size == 0:
                raise ValueError("Empty audio payload")

            audio_duration = audio_array.size / sample_rate if sample_rate else 0.0
            start_timestamp = datetime.utcnow().isoformat() + "Z"

            text, segments, transcription_time = await self.transcriber.transcribe(audio_array, sample_rate)

            response = {
                "type": "transcription",
                "text": text,
                "segments": len(segments),
                "audio_duration": audio_duration,
                "transcription_time": transcription_time,
                "phrase_id": phrase_id,
                "start_timestamp": start_timestamp,
                "end_timestamp": datetime.utcnow().isoformat() + "Z",
            }

            if self.nats_logger:
                await self.nats_logger.log_transcription(
                    text=text,
                    segments=len(segments),
                    audio_duration=audio_duration,
                    transcription_time=transcription_time,
                    start_timestamp=start_timestamp,
                    end_timestamp=response["end_timestamp"],
                )

            await self._reply(msg, response)
            logger.info("Transcription sent for phrase %s", phrase_id or "unknown")

        except Exception as exc:
            logger.error("Failed to transcribe phrase %s: %s", phrase_id or "unknown", exc, exc_info=True)
            await self._reply(
                msg,
                {
                    "type": "transcription",
                    "error": str(exc),
                    "phrase_id": phrase_id,
                },
            )

    async def _reply(self, msg, payload: dict) -> None:
        assert self.nc is not None
        body = json.dumps(payload).encode("utf-8")
        if msg.reply:
            await self.nc.publish(msg.reply, body)
        else:
            await self.nc.publish(self.config.nats.whisper_subject + ".result", body)


async def main() -> None:
    config = ServiceConfig.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    service = WhisperService(config)
    try:
        await service.run()
    except asyncio.CancelledError:
        raise
    except KeyboardInterrupt:
        logger.info("Service interrupted, shutting down")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import asyncio
import json
import logging
import signal
import time
from typing import Any, Optional

import nats
import numpy as np
from faster_whisper import WhisperModel
from nats.aio.msg import Msg

from model_downloader import ensure_model_path
from nats_logger import NatsLogger
from phrase_packet import PhrasePacket


logger = logging.getLogger("whisper_service")


class WhisperService:
    def __init__(
        self,
        *,
        service_name: str,
        nats_url: str,
        frames_subject: str,
        logs_subject: str,
        models_dir,
        model_id: str,
        language: str = "ru",
        device: str = "auto",
        compute_type: str = "default",
        min_phrase_ms: int = 100,
        max_concurrency: int = 1,
        beam_size: int = 5,
    ) -> None:
        self._service_name = service_name
        self._nats_url = nats_url
        self._frames_subject = frames_subject
        self._logs_subject = logs_subject
        self._models_dir = models_dir
        self._model_id = model_id
        self._language = language
        self._device = device
        self._compute_type = compute_type
        self._min_phrase_ms = max(1, min_phrase_ms)
        self._beam_size = max(1, beam_size)
        self._nc: Optional[nats.NATS] = None
        self._nats_logger: Optional[NatsLogger] = None
        self._whisper_model: Optional[WhisperModel] = None
        self._model_lock = asyncio.Lock()
        self._model_path: Optional[str] = None
        self._tasks: set[asyncio.Task] = set()
        self._stop_event = asyncio.Event()
        self._model_task: Optional[asyncio.Task] = None
        self._semaphore = asyncio.Semaphore(max(1, max_concurrency))

    async def run(self) -> None:
        await self._connect()
        self._register_signals()
        await self._stop_event.wait()
        await self._shutdown()

    def stop(self) -> None:
        self._stop_event.set()

    def _register_signals(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, self.stop)
            except NotImplementedError:
                logger.debug("Signal handlers are not supported on this platform")

    async def _connect(self) -> None:
        self._nc = await nats.connect(
            servers=[self._nats_url],
            name=self._service_name,
            max_reconnect_attempts=-1,
            reconnect_time_wait=2,
            ping_interval=10,
        )

        self._nats_logger = NatsLogger(self._nc, self._logs_subject, self._service_name)
        await self._nats_logger.info("Whisper Python service connected")

        self._model_task = asyncio.create_task(self._warmup_model())
        self._model_task.add_done_callback(self._handle_model_task_done)

        await self._nc.subscribe(self._frames_subject, cb=self._handle_message)
        await self._nats_logger.info(f"Subscribed to {self._frames_subject}")

    async def _shutdown(self) -> None:
        if self._model_task:
            self._model_task.cancel()

        for task in list(self._tasks):
            task.cancel()

        if self._nc:
            try:
                await self._nc.drain()
            except Exception:
                await self._nc.close()

    def _handle_model_task_done(self, task: asyncio.Task) -> None:
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("Model preparation failed: %s", exc, exc_info=True)
            asyncio.create_task(self._log_error(f"Model preparation failed: {exc}"))
            self.stop()

    async def _handle_message(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _process_message(self, msg: Msg) -> None:
        if not self._nats_logger:
            return

        try:
            packet = PhrasePacket.from_bytes(msg.data)
        except Exception as exc:
            logger.warning("Invalid packet: %s", exc)
            await self._log_error(f"Invalid packet: {exc}")
            await self._reply(msg, {"error": "invalid_packet", "details": str(exc)})
            return

        try:
            model = await self._ensure_model_loaded()
        except Exception as exc:
            await self._log_error(f"Model not ready: {exc}")
            await self._reply(msg, {"phrase_id": packet.phrase_id, "error": "model_error"})
            return

        await self._nats_logger.info(
            f"Phrase received id={packet.phrase_id} dur={packet.duration:.2f}"
        )

        started = time.perf_counter()
        await self._nats_logger.info(f"Transcription started phrase_id={packet.phrase_id}")

        async with self._semaphore:
            try:
                text = await asyncio.to_thread(self._transcribe, model, packet)
            except Exception as exc:
                logger.exception("Transcription error: %s", exc)
                await self._log_error(f"Transcription error: {exc}")
                await self._reply(
                    msg,
                    {"phrase_id": packet.phrase_id, "error": "transcription_failed", "details": str(exc)},
                )
                return

        transcribe_time = time.perf_counter() - started
        message = {
            "phrase_id": packet.phrase_id,
            "text": text,
            "duration": packet.duration,
            "transcribe_time": transcribe_time,
        }

        await self._nats_logger.info(
            f"Transcription finished phrase_id={packet.phrase_id} time={transcribe_time:.3f}s"
        )
        await self._nats_logger.info(message, name="transcription_result")
        await self._reply(msg, message)

    async def _ensure_model_loaded(self) -> WhisperModel:
        if self._whisper_model:
            return self._whisper_model

        async with self._model_lock:
            if self._whisper_model:
                return self._whisper_model

            assert self._nats_logger is not None
            if not self._model_path:
                self._model_path = await ensure_model_path(
                    self._model_id,
                    self._models_dir,
                    self._nats_logger,
                )

            logger.info("Loading Whisper model from %s", self._model_path)
            await self._nats_logger.info("Model loading", name="model_status")
            try:
                self._whisper_model = await asyncio.to_thread(
                    WhisperModel,
                    self._model_path,
                    device=self._device,
                    compute_type=self._compute_type,
                )
            except Exception as exc:
                await self._nats_logger.error(f"Model load failed: {exc}", name="model_status")
                raise

            await self._nats_logger.info("Model ready", name="model_status")
            return self._whisper_model

    async def _reply(self, msg: Msg, payload: dict[str, Any]) -> None:
        if not msg.reply or not self._nc:
            return
        await self._nc.publish(msg.reply, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    async def _log_error(self, message: str) -> None:
        if self._nats_logger:
            await self._nats_logger.error(message)

    async def _warmup_model(self) -> None:
        try:
            await self._ensure_model_loaded()
        except Exception as exc:
            logger.error("Model warmup failed: %s", exc, exc_info=True)
            await self._log_error(f"Model warmup failed: {exc}")
            self.stop()

    def _transcribe(self, model: WhisperModel, packet: PhrasePacket) -> str:
        audio = np.copy(packet.audio)
        min_samples = int(packet.sample_rate * self._min_phrase_ms / 1000)
        if audio.size < min_samples:
            audio = np.pad(audio, (0, min_samples - audio.size), mode="constant")

        segments, _ = model.transcribe(
            audio,
            language=self._language,
            beam_size=self._beam_size,
            vad_filter=False,
            without_timestamps=True,
        )

        text_parts = [segment.text.strip() for segment in segments if segment.text]
        return " ".join(text_parts).strip()

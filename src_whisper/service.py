from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import time
import uuid
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

import nats
import numpy as np
from faster_whisper import WhisperModel
from nats.aio.msg import Msg

from src_whisper.utils.model_downloader import ensure_model_path
from src_whisper.utils.nats_logger import NatsLogger
from src_whisper.utils.audio_utils import resample_audio
from src_whisper.utils.silero_onnx_vad import SileroOnnxVAD, download_model_file, get_speech_timestamps
from src_whisper.utils.wire_packet import parse_wire_packet
from src_whisper.utils.phrase_packet import PhrasePacket


logger = logging.getLogger("whisper_service")


@dataclass(slots=True)
class StreamState:
    out_subject: str
    session_id: str | None
    buffer: list[np.ndarray]
    buffer_sample_rate: int
    buffer_samples: int
    check_in_progress: bool = False
    flush_requested: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class WhisperService:
    def __init__(
        self,
        *,
        service_name: str,
        nats_url: str,
        asr_in_subscribe: str,
        asr_in_prefix: str,
        asr_out_prefix: str,
        logs_subject: str,
        models_dir,
        model_id: str,
        language: str = "ru",
        device: str = "auto",
        compute_type: str = "default",
        min_phrase_ms: int = 100,
        max_concurrency: int = 1,
        beam_size: int = 1,
        vad_models_dir: str | Path = "/app/models/vad",
        vad_model_url: str = "https://github.com/snakers4/silero-vad/raw/refs/heads/master/src/silero_vad/data/silero_vad.onnx",
        vad_sample_rate: int = 16000,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 500,
        max_speech_duration_s: float = 30.0,
        speech_pad_ms: int = 30,
        vad_threshold: float = 0.8,
        buffer_check_interval_s: float = 1.0,
    ) -> None:
        self._service_name = service_name
        self._nats_url = nats_url
        self._asr_in_subscribe = str(asr_in_subscribe)
        self._asr_in_prefix = str(asr_in_prefix)
        self._asr_out_prefix = str(asr_out_prefix)
        self._events_subject = logs_subject
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

        self._vad_models_dir = Path(vad_models_dir)
        self._vad_model_url = vad_model_url
        self._vad_sample_rate = int(vad_sample_rate)
        self._min_speech_duration_ms = int(min_speech_duration_ms)
        self._min_silence_duration_ms = int(min_silence_duration_ms)
        self._max_speech_duration_s = float(max_speech_duration_s)
        self._speech_pad_ms = int(speech_pad_ms)
        self._vad_threshold = float(vad_threshold)
        self._buffer_check_interval_s = float(buffer_check_interval_s)

        self._vad_model: SileroOnnxVAD | None = None
        self._vad_model_lock = asyncio.Lock()
        self._vad_run_lock = asyncio.Lock()

        self._streams: dict[str, StreamState] = {}

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

        self._nats_logger = NatsLogger(self._nc, self._events_subject, self._service_name)
        await self._nats_logger.info("Whisper Python service connected")

        self._model_task = asyncio.create_task(self._warmup_model())
        self._model_task.add_done_callback(self._handle_model_task_done)

        await self._nc.subscribe(self._asr_in_subscribe, cb=self._handle_message)
        logger.info("Subscribed to: %s", self._asr_in_subscribe)
        await self._nats_logger.info(f"Subscribed to: {self._asr_in_subscribe}")

    async def _shutdown(self) -> None:
        if self._model_task:
            self._model_task.cancel()

        for task in list(self._tasks):
            task.cancel()

        self._streams.clear()
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
            assert self._nats_logger is not None
            asyncio.create_task(self._nats_logger.error(f"Model preparation failed: {exc}"))
            self.stop()

    async def _handle_message(self, msg: Msg) -> None:
        task = asyncio.create_task(self._process_message(msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _derive_out_subject(self, in_subject: str) -> str | None:
        if not in_subject.startswith(self._asr_in_prefix):
            logger.error(
                "Dropping message: subject does not match ASR_IN_PREFIX (subject=%s prefix=%s)",
                in_subject,
                self._asr_in_prefix,
            )
            return None
        suffix = in_subject[len(self._asr_in_prefix) :]
        if not suffix:
            logger.error("Dropping message: empty token suffix in subject=%s", in_subject)
            return None
        return f"{self._asr_out_prefix}{suffix}"

    async def _process_message(self, msg: Msg) -> None:
        if not self._nats_logger:
            return

        out_subject = self._derive_out_subject(str(msg.subject or ""))
        if not out_subject:
            return

        try:
            meta, audio = parse_wire_packet(msg.data)
        except Exception as exc:
            logger.warning("Invalid packet: %s", exc)
            await self._nats_logger.error(f"Invalid packet: {exc}")
            await self._publish_reply(out_subject, {"error": "invalid_packet", "details": str(exc)})
            return

        msg_type = str(meta.get("type") or "phrase")
        # stream_id = meta.get("stream_id") or meta.get("phrase_id") or "-"
        # session_id = meta.get("session_id") or "-"
        # await self._nats_logger.info(
        #     f"Parsed stream_id={stream_id} session_id={session_id} type={msg_type}"
        # )
        if msg_type == "frame":
            await self._handle_stream_frame(out_subject, meta, audio)
            return
        if msg_type == "end":
            await self._handle_stream_end(out_subject, meta)
            return

        try:
            packet = PhrasePacket.from_bytes(msg.data)
        except Exception as exc:
            logger.warning("Invalid phrase packet: %s", exc)
            await self._nats_logger.error(f"Invalid packet: {exc}")
            await self._publish_reply(out_subject, {"error": "invalid_packet", "details": str(exc)})
            return

        try:
            model = await self._ensure_model_loaded()
        except Exception as exc:
            await self._nats_logger.error(f"Model not ready: {exc}")
            await self._publish_reply(out_subject, {"phrase_id": packet.phrase_id, "error": "model_error"})
            return

        await self._nats_logger.info(f"Phrase received id={packet.phrase_id} dur={packet.duration:.2f}")

        started = time.perf_counter()
        await self._nats_logger.info(f"Transcription started phrase_id={packet.phrase_id}")

        session_id = meta.get("session_id")
        async with self._semaphore:
            try:
                text = await asyncio.to_thread(self._transcribe, model, packet)
            except Exception as exc:
                logger.exception("Transcription error: %s", exc)
                await self._nats_logger.error(f"Transcription error: {exc}")
                await self._publish_reply(
                    out_subject,
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
        if session_id:
            message["session_id"] = str(session_id)

        await self._nats_logger.log(
            "log",
            "info",
            {"text": f"Transcription finished phrase_id={packet.phrase_id} time={transcribe_time:.3f}s"},
        )
        await self._nats_logger.log(
            "log",
            "info",
            {"text": text},
            name="transcription_result",
        )
        await self._publish_reply(out_subject, message)

    async def _handle_stream_frame(self, out_subject: str, meta: dict[str, Any], audio: np.ndarray) -> None:
        if not self._nats_logger:
            return

        stream_id = out_subject
        session_id = meta.get("session_id")
        sr = int(meta.get("sample_rate") or self._vad_sample_rate)

        state = self._streams.get(stream_id)
        if not state:
            state = StreamState(
                out_subject=out_subject,
                session_id=str(session_id) if session_id else None,
                buffer=[],
                buffer_sample_rate=sr,
                buffer_samples=0,
            )
            self._streams[stream_id] = state
            await self._nats_logger.info(f"Stream opened out_subject={out_subject}")

        schedule_check = False
        async with state.lock:
            state.out_subject = out_subject
            if session_id and not state.session_id:
                state.session_id = str(session_id)
            if sr:
                state.buffer_sample_rate = sr

            if audio.size:
                state.buffer.append(audio)
                state.buffer_samples += int(audio.size)

            buffer_duration = (
                state.buffer_samples / max(1, state.buffer_sample_rate)
                if state.buffer_samples
                else 0.0
            )
            schedule_check = buffer_duration >= self._buffer_check_interval_s and not state.check_in_progress

        if schedule_check:
            task = asyncio.create_task(self._check_stream_buffer(stream_id, flush=False))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _handle_stream_end(self, out_subject: str, meta: dict[str, Any]) -> None:
        stream_id = out_subject
        state = self._streams.get(stream_id)
        if not state:
            return

        schedule_check = False
        async with state.lock:
            state.flush_requested = True
            schedule_check = not state.check_in_progress

        if schedule_check:
            task = asyncio.create_task(self._check_stream_buffer(stream_id, flush=True))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

    async def _check_stream_buffer(self, stream_id: str, *, flush: bool) -> None:
        state = self._streams.get(stream_id)
        if not state:
            return

        async with state.lock:
            if state.check_in_progress:
                return
            state.check_in_progress = True
            effective_flush = bool(flush or state.flush_requested)
            snapshot_chunks = list(state.buffer)
            snapshot_samples = int(state.buffer_samples)
            snapshot_sr = int(state.buffer_sample_rate or self._vad_sample_rate)

        try:
            if not snapshot_chunks:
                return

            audio = np.concatenate(snapshot_chunks)
            source_sr = snapshot_sr
            target_sr = int(self._vad_sample_rate)
            if source_sr != target_sr:
                audio = resample_audio(audio, source_sr, target_sr)

            if not effective_flush and (len(audio) / target_sr) < 1.0:
                return

            timestamps = await self._get_timestamps(audio)
            if not timestamps:
                if (len(audio) / target_sr) > 5.0:
                    async with state.lock:
                        del state.buffer[: len(snapshot_chunks)]
                        state.buffer_samples = max(0, int(state.buffer_samples) - snapshot_samples)
                return

            should_flush = effective_flush
            if not should_flush:
                last_end_sample = int(timestamps[-1]["end"])
                silence_after = (len(audio) - last_end_sample) / target_sr
                should_flush = silence_after >= (self._min_silence_duration_ms / 1000.0)
            if not should_flush:
                return

            async with state.lock:
                out_subject = state.out_subject
                session_id = state.session_id

            for ts in timestamps:
                start_sample = int(ts["start"])
                end_sample = int(ts["end"])
                segment_audio = audio[start_sample:end_sample]
                duration = float(len(segment_audio) / target_sr) if target_sr else 0.0
                phrase_id = str(uuid.uuid4())

                packet = PhrasePacket(
                    phrase_id=phrase_id,
                    sample_rate=target_sr,
                    duration=duration,
                    audio=segment_audio,
                )
                task = asyncio.create_task(
                    self._transcribe_and_publish(out_subject, session_id, packet)
                )
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

            async with state.lock:
                del state.buffer[: len(snapshot_chunks)]
                state.buffer_samples = max(0, int(state.buffer_samples) - snapshot_samples)
        finally:
            needs_final_flush = False
            async with state.lock:
                state.check_in_progress = False
                needs_final_flush = bool(state.flush_requested and not flush)

            if effective_flush:
                self._streams.pop(stream_id, None)
            elif needs_final_flush:
                task = asyncio.create_task(self._check_stream_buffer(stream_id, flush=True))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

    async def _transcribe_and_publish(
        self,
        reply_subject: str,
        session_id: str | None,
        packet: PhrasePacket,
    ) -> None:
        if not self._nats_logger:
            return

        try:
            model = await self._ensure_model_loaded()
        except Exception as exc:
            await self._nats_logger.error(f"Model not ready: {exc}")
            await self._publish_reply(reply_subject, {"phrase_id": packet.phrase_id, "error": "model_error"})
            return

        started = time.perf_counter()
        async with self._semaphore:
            try:
                text = await asyncio.to_thread(self._transcribe, model, packet)
            except Exception as exc:
                logger.exception("Transcription error: %s", exc)
                await self._nats_logger.error(f"Transcription error: {exc}")
                await self._publish_reply(
                    reply_subject,
                    {"phrase_id": packet.phrase_id, "error": "transcription_failed", "details": str(exc)},
                )
                return

        transcribe_time = time.perf_counter() - started
        message: dict[str, Any] = {
            "phrase_id": packet.phrase_id,
            "text": text,
            "duration": packet.duration,
            "transcribe_time": transcribe_time,
        }
        if session_id:
            message["session_id"] = session_id

        await self._publish_reply(reply_subject, message)

    async def _publish_reply(self, subject: str, payload: dict[str, Any]) -> None:
        if not self._nc:
            return
        await self._nc.publish(subject, json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    async def _get_timestamps(self, audio_array: np.ndarray) -> list[dict[str, Any]]:
        await self._ensure_vad_loaded()
        if not self._vad_model:
            return []

        async with self._vad_run_lock:
            return await asyncio.to_thread(
                get_speech_timestamps,
                audio_array,
                self._vad_model,
                threshold=self._vad_threshold,
                sampling_rate=self._vad_sample_rate,
                min_speech_duration_ms=self._min_speech_duration_ms,
                min_silence_duration_ms=self._min_silence_duration_ms,
                max_speech_duration_s=self._max_speech_duration_s,
                speech_pad_ms=self._speech_pad_ms,
                return_seconds=False,
            )

    async def _ensure_vad_loaded(self) -> None:
        if self._vad_model:
            return
        async with self._vad_model_lock:
            if self._vad_model:
                return

            if self._nats_logger:
                await self._nats_logger.log("command", "status_vad", {"status": "downloading"})

            url = self._vad_model_url
            filename = os.path.basename(urlparse(url).path)
            base_path = self._vad_models_dir.expanduser()
            model_path = base_path if base_path.suffix.lower() == ".onnx" else (base_path / filename)
            model_path.parent.mkdir(parents=True, exist_ok=True)

            if not model_path.exists():
                await asyncio.to_thread(download_model_file, str(model_path), url)

            self._vad_model = await asyncio.to_thread(SileroOnnxVAD, str(model_path))
            if self._nats_logger:
                await self._nats_logger.info(f"Silero VAD model loaded from {model_path}")
                await self._nats_logger.log("command", "status_vad", {"status": "ready"})

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

    async def _warmup_model(self) -> None:
        try:
            await self._ensure_model_loaded()
        except Exception as exc:
            logger.error("Model warmup failed: %s", exc, exc_info=True)
            assert self._nats_logger is not None
            await self._nats_logger.error(f"Model warmup failed: {exc}")
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

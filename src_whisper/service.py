"""
Главный сервис Whisper: обработка входящих фраз и публикация результатов.
"""

from __future__ import annotations

import asyncio
import json
import logging
import traceback
from datetime import datetime
from typing import Awaitable, Optional

import nats
from nats.aio.msg import Msg

from config import ServiceConfig
from utils.nats_log_handler import NatsLogHandler
from utils.nats_logger import NatsLogger
from phrases import PhrasePacket, PhrasePacketError
from transcriber import WhisperTranscriber


logger = logging.getLogger("whisper.service")
SERVICE_NAME = "src_whisper"


class WhisperService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.nc: Optional[nats.NATS] = None
        self.transcriber = WhisperTranscriber(config.whisper.model_path)
        self.nats_logger: Optional[NatsLogger] = None
        self._log_tasks: set[asyncio.Task[None]] = set()

    async def run(self) -> None:
        await self._connect()
        await self._setup_logging()
        await self.transcriber.load()

        assert self.nc is not None
        subject = self.config.nats.whisper_subject
        await self.nc.subscribe(subject, cb=self._handle_phrase)
        logger.info("Listening for phrases on %s", subject)

        await asyncio.Event().wait()

    async def _connect(self) -> None:
        urls = [url.strip() for url in str(self.config.nats.url).split(",") if url.strip()]
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
            service_name=SERVICE_NAME,
        )

    async def _handle_phrase(self, msg: Msg) -> None:
        packet: PhrasePacket | None = None
        try:
            packet = PhrasePacket.from_bytes(msg.data)
            self._schedule_log(self._log_phrase_received(packet), "phrase_received")
        except PhrasePacketError as exc:
            logger.error("Failed to parse phrase: %s", exc)
            self._schedule_log(
                self._log_error(
                    event="phrase_parse_failed",
                    exc=exc,
                    payload_size=len(msg.data),
                ),
                "phrase_parse_failed",
            )
            await self._reply_with_error(msg, str(exc))
            return
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected phrase parsing error")
            self._schedule_log(
                self._log_error(
                    event="phrase_receive_error",
                    exc=exc,
                    payload_size=len(msg.data),
                ),
                "phrase_receive_error",
            )
            await self._reply_with_error(msg, str(exc))
            return

        start_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

        self._schedule_log(
            self._log_transcription_start(packet, start_timestamp),
            "transcription_started",
        )
        try:
            result = await self.transcriber.transcribe(packet.audio, packet.sample_rate)
            end_timestamp = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            payload = self._build_response(packet, result, start_timestamp, end_timestamp)
            self._schedule_log(
                self._log_transcription_complete(
                    packet,
                    result,
                    start_timestamp,
                    payload["end_timestamp"],
                ),
                "transcription_completed",
            )
            await self._reply(msg, payload)
            logger.info("Transcription sent for phrase %s", packet.phrase_id or "unknown")
        except Exception as exc:
            logger.exception("Transcription failed")
            self._schedule_log(
                self._log_error(
                    event="transcription_failed",
                    exc=exc,
                    phrase_id=packet.phrase_id,
                    sample_rate=packet.sample_rate,
                    audio_duration=packet.duration,
                ),
                "transcription_failed",
            )
            await self._reply_with_error(msg, str(exc), packet.phrase_id)

    async def _emit_transcription_log(self, packet: PhrasePacket, result, start_ts: str, end_ts: str) -> None:
        if not self.nats_logger or not result.text:
            return
        await self.nats_logger.log_transcription(
            text=result.text,
            segments=len(result.segments),
            audio_duration=result.audio_duration,
            transcription_time=result.transcription_time,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
            phrase_id=packet.phrase_id,
        )

    async def _log_phrase_received(self, packet: PhrasePacket) -> None:
        if not self.nats_logger:
            return
        await self.nats_logger.log_event(
            event_type="phrase_received",
            message="Получена фраза из NATS",
            category="transcription",
            phrase_id=packet.phrase_id,
            sample_rate=packet.sample_rate,
            audio_duration=round(packet.duration, 3),
            audio_samples=int(packet.audio.size),
            metadata=packet.metadata,
        )

    async def _log_transcription_start(self, packet: PhrasePacket, start_timestamp: str) -> None:
        if not self.nats_logger:
            return
        await self.nats_logger.log_transcription_start(
            audio_duration=packet.duration,
            audio_samples=int(packet.audio.size),
            sample_rate=packet.sample_rate,
            phrase_id=packet.phrase_id,
            start_timestamp=start_timestamp,
            metadata=packet.metadata,
        )

    async def _log_transcription_complete(
        self,
        packet: PhrasePacket,
        result,
        start_ts: str,
        end_ts: str,
    ) -> None:
        await self._emit_transcription_log(packet, result, start_ts, end_ts)

    async def _log_error(
        self,
        *,
        event: str,
        exc: Exception,
        phrase_id: str | None = None,
        **extra,
    ) -> None:
        if not self.nats_logger:
            return
        payload = {
            "event": event,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "stacktrace": traceback.format_exc(),
        }
        if phrase_id:
            payload["phrase_id"] = phrase_id
        if extra:
            payload.update(extra)
        await self.nats_logger.log_error(
            f"{event}: {exc}",
            category="whisper",
            **payload,
        )

    def _build_response(self, packet: PhrasePacket, result, start_ts: str, end_timestamp) -> dict:

        return {
            "type": "transcription",
            "service": SERVICE_NAME,
            "timestamp": end_timestamp,
            "phrase_id": packet.phrase_id,
            "text": result.text,
            "segments": len(result.segments),
            "audio_duration": result.audio_duration,
            "transcription_time": result.transcription_time,
            "start_timestamp": start_ts,
            "end_timestamp": end_timestamp,
        }

    async def _reply(self, msg: Msg, payload: dict) -> None:
        assert self.nc is not None
        body = json.dumps(payload).encode("utf-8")
        if msg.reply:
            await self.nc.publish(msg.reply, body)
        else:
            await self.nc.publish(self.config.nats.whisper_subject + ".result", body)

    async def _reply_with_error(self, msg: Msg, error: str, phrase_id: str | None = None) -> None:
        await self._reply(
            msg,
            {
                "type": "transcription",
                "error": error,
                "phrase_id": phrase_id,
            },
        )

    def _schedule_log(self, coro: Awaitable[None] | None, context: str) -> None:
        if coro is None:
            return
        task = asyncio.create_task(coro, name=f"log:{context}")
        self._log_tasks.add(task)

        def _on_done(t: asyncio.Task[None], label: str) -> None:
            self._log_tasks.discard(t)
            try:
                exc = t.exception()
            except Exception:  # pragma: no cover
                logger.exception("Failed to fetch exception from log task %s", label)
                return
            if exc:
                logger.warning("Log task %s failed: %s", label, exc)

        task.add_done_callback(lambda t, lbl=context: _on_done(t, lbl))

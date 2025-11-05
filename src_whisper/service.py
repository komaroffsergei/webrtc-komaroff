"""
Главный сервис Whisper: обработка входящих фраз и публикация результатов.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional

import nats
from nats.aio.msg import Msg

from config import ServiceConfig
from src_whisper.utils.nats_log_handler import NatsLogHandler
from src_whisper.utils.nats_logger import NatsLogger
from phrases import PhrasePacket, PhrasePacketError
from transcriber import WhisperTranscriber


logger = logging.getLogger("whisper.service")


class WhisperService:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.nc: Optional[nats.NATS] = None
        self.transcriber = WhisperTranscriber(config.whisper.model_path)
        self.nats_logger: Optional[NatsLogger] = None

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
            service_name="whisper",
        )

    async def _handle_phrase(self, msg: Msg) -> None:
        try:
            packet = PhrasePacket.from_bytes(msg.data)
        except PhrasePacketError as exc:
            logger.error("Failed to parse phrase: %s", exc)
            await self._reply_with_error(msg, str(exc))
            return
        except Exception as exc:  # pragma: no cover
            logger.exception("Unexpected phrase parsing error")
            await self._reply_with_error(msg, str(exc))
            return

        start_timestamp = datetime.utcnow().isoformat() + "Z"

        try:
            result = await self.transcriber.transcribe(packet.audio, packet.sample_rate)
            payload = self._build_response(packet, result, start_timestamp)
            await self._emit_transcription_log(result, start_timestamp, payload["end_timestamp"])
            await self._reply(msg, payload)
            logger.info("Transcription sent for phrase %s", packet.phrase_id or "unknown")
        except Exception as exc:
            logger.exception("Transcription failed")
            await self._reply_with_error(msg, str(exc), packet.phrase_id)

    async def _emit_transcription_log(self, result, start_ts: str, end_ts: str) -> None:
        if not self.nats_logger or not result.text:
            return
        await self.nats_logger.log_transcription(
            text=result.text,
            segments=len(result.segments),
            audio_duration=result.audio_duration,
            transcription_time=result.transcription_time,
            start_timestamp=start_ts,
            end_timestamp=end_ts,
        )

    def _build_response(self, packet: PhrasePacket, result, start_ts: str) -> dict:
        end_timestamp = datetime.utcnow().isoformat() + "Z"
        return {
            "type": "transcription",
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

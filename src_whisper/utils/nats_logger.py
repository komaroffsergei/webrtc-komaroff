"""
Простой логгер для отправки событий в формате {time, service, type, message}.
Использование:

    nats_logger = NatsLogger(nc, subject="whisper.logs", service_name="src_whisper")
    await nats_logger.log_info("Whisper ready")
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from nats.aio.client import Client as NATS

log = logging.getLogger(__name__)


class NatsLogger:
    """Легковесный логгер отправляющий сообщения одного вида."""

    def __init__(self, nc: NATS, subject: str, service_name: str = "unknown") -> None:
        self.nc = nc
        self.subject = subject
        self.service_name = service_name

    async def _publish(self, log_type: str, message: str) -> None:
        if not self.nc or not self.nc.is_connected:
            log.warning("NATS not connected, skipping log: %s", message)
            return

        entry = {
            "time": datetime.utcnow().isoformat() + "Z",
            "service": self.service_name,
            "type": log_type,
            "message": message,
        }

        try:
            await self.nc.publish(self.subject, json.dumps(entry).encode("utf-8"))
        except Exception as exc:  # pragma: no cover
            log.error("Failed to publish log to NATS: %s", exc)

    async def log_debug(self, message: str) -> None:
        await self._publish("debug", message)

    async def log_info(self, message: str) -> None:
        await self._publish("info", message)

    async def log_warning(self, message: str) -> None:
        await self._publish("warning", message)

    async def log_error(self, message: str) -> None:
        await self._publish("error", message)

    async def log_status(self, value: str) -> None:
        await self._publish("status", value)

    async def log_transcription_start(
        self,
        phrase_id: str | None,
        duration: float,
        samples: int,
        sample_rate: int,
        start_timestamp: str | None = None,
    ) -> str:
        ts = start_timestamp or datetime.utcnow().isoformat() + "Z"
        parts = [
            "Transcription started",
            f"phrase_id={phrase_id or 'unknown'}",
            f"duration={duration:.2f}s",
            f"samples={samples}",
            f"sample_rate={sample_rate}",
            f"start={ts}",
        ]
        await self.log_info(" | ".join(parts))
        return ts

    async def log_transcription_complete(
        self,
        phrase_id: str | None,
        text: str,
        segments: int,
        audio_duration: float,
        transcription_time: float,
        start_ts: str,
        end_ts: str,
    ) -> None:
        clean_text = " ".join(text.strip().split())
        if len(clean_text) > 120:
            clean_text = clean_text[:117] + "..."

        summary = (
            f"Transcription completed phrase_id={phrase_id or 'unknown'} "
            f"segments={segments} audio={audio_duration:.2f}s time={transcription_time:.2f}s "
            f"{start_ts}->{end_ts} text=\"{clean_text}\""
        )
        await self.log_info(summary)

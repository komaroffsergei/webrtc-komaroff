"""
Унифицированная система логирования в NATS для межсервисного обмена логами.
Использование:
    from nats_logger import NatsLogger
    
    nats_logger = NatsLogger(nc, subject="service.logs")
    await nats_logger.log_info("Operation completed", category="system", extra={"duration": 1.23})
    await nats_logger.log_transcription("Hello world", segments=2, audio_duration=3.45, transcription_time=1.23)
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from nats.aio.client import Client as NATS

log = logging.getLogger(__name__)


class NatsLogger:
    """
    Унифицированный логгер для отправки структурированных логов в NATS.
    Логи автоматически получают timestamp, uid и отправляются в указанный subject.
    """
    
    def __init__(self, nc: NATS, subject: str, service_name: str = "unknown"):
        """
        Args:
            nc: NATS клиент
            subject: NATS subject для логов (например, "whisper.logs")
            service_name: Имя сервиса для идентификации источника логов
        """
        self.nc = nc
        self.subject = subject
        self.service_name = service_name
    
    async def _publish_log(
        self,
        level: str,
        message: str,
        category: str = "general",
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Базовый метод отправки лога в NATS.
        
        Args:
            level: Уровень лога (debug, info, warning, error)
            message: Текст сообщения
            category: Категория (system, webrtc, nats, audio, whisper, general)
            extra: Дополнительные поля для включения в лог
        """
        if not self.nc or not self.nc.is_connected:
            log.warning(f"NATS not connected, skipping log: {message}")
            return
        
        log_data = {
            "type": "log",
            "level": level,
            "category": category,
            "message": message,
            "service": self.service_name,
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if extra:
            log_data.update(extra)
        
        try:
            await self.nc.publish(self.subject, json.dumps(log_data).encode("utf-8"))
        except Exception as e:
            log.error(f"Failed to publish log to NATS: {e}")
    
    async def log_debug(
        self,
        message: str,
        category: str = "general",
        **kwargs
    ) -> None:
        """Отправить DEBUG лог."""
        await self._publish_log("debug", message, category, kwargs if kwargs else None)
    
    async def log_info(
        self,
        message: str,
        category: str = "general",
        **kwargs
    ) -> None:
        """Отправить INFO лог."""
        await self._publish_log("info", message, category, kwargs if kwargs else None)
    
    async def log_warning(
        self,
        message: str,
        category: str = "general",
        **kwargs
    ) -> None:
        """Отправить WARNING лог."""
        await self._publish_log("warning", message, category, kwargs if kwargs else None)
    
    async def log_error(
        self,
        message: str,
        category: str = "general",
        **kwargs
    ) -> None:
        """Отправить ERROR лог."""
        await self._publish_log("error", message, category, kwargs if kwargs else None)
    
    async def log_transcription(
        self,
        text: str,
        segments: int,
        audio_duration: float,
        transcription_time: float,
        start_timestamp: Optional[str] = None,
        end_timestamp: Optional[str] = None
    ) -> None:
        """
        Специализированный метод для логирования транскрипции.
        
        Args:
            text: Транскрибированный текст
            segments: Количество сегментов
            audio_duration: Длительность аудио (секунды)
            transcription_time: Время транскрипции (секунды)
            start_timestamp: ISO timestamp начала транскрипции
            end_timestamp: ISO timestamp окончания транскрипции
        """
        rtf = transcription_time / audio_duration if audio_duration > 0 else 0
        
        extra = {
            "text": text,
            "segments": segments,
            "audio_duration": audio_duration,
            "transcription_time": transcription_time,
            "rtf": round(rtf, 2)
        }
        
        if start_timestamp:
            extra["start"] = start_timestamp
        if end_timestamp:
            extra["end"] = end_timestamp
        
        message = (
            f"Transcription completed: audio_duration={audio_duration:.2f}s "
            f"transcription_time={transcription_time:.2f}s segments={segments}"
        )
        
        if start_timestamp and end_timestamp:
            message += f" start={start_timestamp} end={end_timestamp}"
        
        await self._publish_log("info", message, "whisper", extra)
    
    async def log_transcription_start(
        self,
        audio_duration: float,
        audio_bytes: int
    ) -> str:
        """
        Логировать начало транскрипции.
        
        Args:
            audio_duration: Длительность аудио (секунды)
            audio_bytes: Размер аудио данных (байты)
        
        Returns:
            ISO timestamp начала транскрипции
        """
        start_timestamp = datetime.utcnow().isoformat() + "Z"
        
        message = f"Transcription started: audio_duration={audio_duration:.2f}s bytes={audio_bytes}"
        
        await self._publish_log(
            "info",
            message,
            "whisper",
            {
                "audio_duration": audio_duration,
                "audio_bytes": audio_bytes,
                "start": start_timestamp
            }
        )
        
        return start_timestamp
    
    async def log_event(
        self,
        event_type: str,
        message: str,
        category: str = "system",
        level: str = "info",
        **kwargs
    ) -> None:
        """
        Логировать произвольное событие с дополнительными полями.
        
        Args:
            event_type: Тип события (например, "connection", "error", "metric")
            message: Описание события
            category: Категория события
            level: Уровень важности
            **kwargs: Произвольные дополнительные поля
        """
        extra = {"event_type": event_type}
        if kwargs:
            extra.update(kwargs)
        
        await self._publish_log(level, message, category, extra)

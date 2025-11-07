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
        end_timestamp: Optional[str] = None,
        phrase_id: Optional[str] = None,
        event_type: str = "transcription_completed",
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
            "rtf": round(rtf, 2),
            "event": event_type,
        }
        if phrase_id:
            extra["phrase_id"] = phrase_id
        
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
        audio_samples: int,
        sample_rate: int,
        phrase_id: Optional[str] = None,
        start_timestamp: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Логировать начало транскрипции.
        
        Args:
            audio_duration: Длительность аудио (секунды)
            audio_samples: Количество сэмплов в аудио
            sample_rate: Частота дискретизации входного аудио
            phrase_id: Идентификатор фразы (если есть)
            start_timestamp: Готовый timestamp (ISO). Если не указан, будет создан автоматически.
            metadata: Дополнительные метаданные фразы для отображения в логах
        
        Returns:
            ISO timestamp начала транскрипции
        """
        ts = start_timestamp or datetime.utcnow().isoformat() + "Z"
        payload: Dict[str, Any] = {
            "audio_duration": audio_duration,
            "audio_samples": audio_samples,
            "sample_rate": sample_rate,
            "start": ts,
            "event": "transcription_started",
        }
        if phrase_id:
            payload["phrase_id"] = phrase_id
        if metadata:
            payload["metadata"] = metadata

        message = (
            f"Transcription started: audio_duration={audio_duration:.2f}s "
            f"samples={audio_samples} sample_rate={sample_rate}"
        )

        await self._publish_log("info", message, "whisper", payload)
        return ts
    
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
            event_type: Тип события (будет записан в поле 'event')
            message: Описание события
            category: Категория события
            level: Уровень важности
            **kwargs: Произвольные дополнительные поля
        """
        extra = {"event": event_type}
        if kwargs:
            extra.update(kwargs)
        
        await self._publish_log(level, message, category, extra)

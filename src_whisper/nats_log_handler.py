"""
NATS Log Handler - отправка логов в NATS для вывода через SSE
"""

import logging
import json
import asyncio
from datetime import datetime
from typing import Optional


class NatsLogHandler(logging.Handler):
    """
    Handler для отправки логов в NATS.
    """

    def __init__(self, nats_client, subject: str, level=logging.INFO):
        """
        Args:
            nats_client: NATS клиент
            subject: subject для отправки логов
            level: минимальный уровень логирования
        """
        super().__init__(level)
        self.nats_client = nats_client
        self.subject = subject
        self.loop = None

    def emit(self, record: logging.LogRecord) -> None:
        """Отправить лог в NATS."""
        try:
            # Форматируем лог
            log_entry = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno
            }
            
            # Добавляем exception info если есть
            if record.exc_info:
                log_entry["exception"] = self.format(record)
            
            # Отправляем в NATS
            message = json.dumps(log_entry).encode("utf-8")
            
            # Если loop не установлен, пытаемся получить текущий
            if self.loop is None:
                try:
                    self.loop = asyncio.get_event_loop()
                except RuntimeError:
                    return
            
            # Отправляем асинхронно
            if self.loop and self.loop.is_running():
                asyncio.create_task(self._async_publish(message))
                
        except Exception:
            self.handleError(record)

    async def _async_publish(self, message: bytes) -> None:
        """Асинхронная отправка в NATS."""
        try:
            if self.nats_client and self.nats_client.is_connected:
                await self.nats_client.publish(self.subject, message)
        except Exception:
            pass  # Не падаем если не удалось отправить лог

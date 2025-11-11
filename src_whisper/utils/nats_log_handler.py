"""
NATS Log Handler - обработчик для отправки логов Python в NATS
Использует logging.Handler для интеграции с стандартной системой логирования.
"""

import asyncio
import json
import logging
from datetime import datetime


class NatsLogHandler(logging.Handler):
    """
    Logging handler для отправки логов в NATS.
    Автоматически форматирует и отправляет логи в указанный subject.
    """

    def __init__(self, nats_client, subject: str, service_name: str, level=logging.INFO):
        """
        Args:
            nats_client: NATS клиент (nats.aio.client.Client)
            subject: NATS subject для отправки логов
            level: минимальный уровень логирования
        """
        super().__init__(level)
        self.nats_client = nats_client
        self.subject = subject
        self.service_name = service_name
        self.loop = None

    def emit(self, record: logging.LogRecord) -> None:
        """
        Отправить лог запись в NATS.
        
        Args:
            record: логируемая запись
        """
        try:
            message_text = record.getMessage()
            if record.exc_info:
                exc_text = self.formatException(record.exc_info)
                message_text = f"{message_text} | {exc_text}"

            log_entry = {
                "time": datetime.utcnow().isoformat() + "Z",
                "service": self.service_name,
                "type": record.levelname.lower(),
                "message": message_text,
            }

            message = json.dumps(log_entry).encode("utf-8")
            
            # Получить event loop
            if self.loop is None:
                try:
                    self.loop = asyncio.get_running_loop()
                except RuntimeError:
                    # Нет running loop - пропускаем
                    return
            
            # Проверить что loop работает
            if self.loop and self.loop.is_running():
                # Создать task в правильном loop
                asyncio.run_coroutine_threadsafe(
                    self._async_publish(message),
                    self.loop
                )
                
        except Exception:
            # Тихо игнорируем ошибки логирования
            pass

    async def _async_publish(self, message: bytes) -> None:
        """
        Асинхронная отправка сообщения в NATS.
        
        Args:
            message: сериализованное сообщение
        """
        try:
            if self.nats_client and self.nats_client.is_connected:
                await self.nats_client.publish(self.subject, message)
        except Exception:
            pass

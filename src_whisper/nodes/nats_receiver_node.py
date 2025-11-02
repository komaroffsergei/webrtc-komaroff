"""
NATS Receiver Node - получение аудио фреймов из NATS
"""

import asyncio
import json
import nats
from typing import Optional

from .base_node import BaseNode


class NatsReceiverNode(BaseNode):
    """
    Нода для получения аудио фреймов из NATS.
    Выход: {"audio": bytes, "meta": dict}
    """

    def __init__(
        self,
        nats_url: str,
        subject: str,
        name: str = "nats_receiver"
    ):
        """
        Args:
            nats_url: URL NATS сервера
            subject: subject для подписки
            name: имя ноды
        """
        super().__init__(name)
        self.nats_url = nats_url
        self.subject = subject
        self.nc: Optional[nats.Client] = None
        self.subscription = None

    async def start(self) -> None:
        """Подключиться к NATS и начать прием."""
        try:
            # Подключение к NATS
            urls = [u.strip() for u in str(self.nats_url).split(",") if u.strip()]
            self.nc = await nats.connect(
                servers=urls or [self.nats_url],
                max_reconnect_attempts=-1,
                reconnect_time_wait=2,
                ping_interval=10,
            )
            
            self.logger.info(f"Connected to NATS: {self.nc.connected_url.netloc}")
            
            # Подписка на subject
            self.subscription = await self.nc.subscribe(self.subject, cb=self._message_handler)
            self.logger.info(f"Subscribed to {self.subject}")
            
        except Exception as e:
            self.logger.error(f"Failed to start NATS receiver: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Отключиться от NATS."""
        if self.subscription:
            try:
                await self.subscription.unsubscribe()
            except Exception:
                pass
        
        if self.nc:
            try:
                await self.nc.drain()
                await self.nc.close()
            except Exception:
                pass
        
        self.logger.info("NATS receiver stopped")

    async def _message_handler(self, msg: nats.aio.client.Msg) -> None:
        """
        Обработчик входящих сообщений из NATS.
        
        Args:
            msg: NATS сообщение
        """
        try:
            meta, audio = self._decode_payload(msg.data)
            
            if meta is None or audio is None:
                self.logger.warning("Invalid payload, skipping")
                return
            
            # Передаем данные дальше
            await self.emit({
                "audio": audio,
                "meta": meta
            })
            
        except Exception as e:
            self.logger.error(f"Error handling NATS message: {e}", exc_info=True)

    def _decode_payload(self, data: bytes) -> tuple:
        """
        Декодировать payload из NATS.
        
        Args:
            data: сырые байты из NATS
        
        Returns:
            tuple[meta, audio]: метаданные и аудио данные
        """
        if len(data) < 4:
            return None, None
        
        try:
            meta_len = int.from_bytes(data[:4], "big")
            end = 4 + meta_len
            
            if end > len(data):
                return None, None
            
            meta = json.loads(data[4:end].decode("utf-8"))
            audio = data[end:]
            
            return meta, audio
            
        except Exception as e:
            self.logger.debug(f"Error decoding payload: {e}")
            return None, None

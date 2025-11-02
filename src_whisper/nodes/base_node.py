"""
Base Node - базовый класс для всех нод обработки
"""

import logging
from typing import Callable, Any, Optional, Awaitable
from abc import ABC, abstractmethod


class BaseNode(ABC):
    """
    Базовый класс для нод обработки.
    Каждая нода выполняет одну задачу и передает результат через callback.
    """

    def __init__(self, name: str):
        """
        Args:
            name: имя ноды для логирования
        """
        self.name = name
        self.logger = logging.getLogger(f"whisper.nodes.{name}")
        self.callback: Optional[Callable[[Any], Awaitable[None]]] = None

    def set_callback(self, callback: Callable[[Any], Awaitable[None]]) -> None:
        """
        Установить callback для передачи результатов.
        
        Args:
            callback: async функция для обработки результата
        """
        self.callback = callback
        self.logger.debug(f"Callback set for {self.name}")

    async def emit(self, data: Any) -> None:
        """
        Передать данные в callback.
        
        Args:
            data: данные для передачи
        """
        if self.callback:
            try:
                await self.callback(data)
            except Exception as e:
                self.logger.error(f"Error in callback: {e}", exc_info=True)
        else:
            self.logger.warning(f"No callback set for {self.name}, data dropped")

    @abstractmethod
    async def start(self) -> None:
        """Запустить ноду."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Остановить ноду."""
        pass

    async def process(self, data: Any) -> None:
        """
        Обработать входные данные.
        Должен быть переопределен в дочерних классах если нода принимает данные.
        
        Args:
            data: входные данные
        """
        pass

"""
Command Registry - реестр голосовых команд
"""

import logging
import re
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger("whisper.command_registry")


@dataclass
class VoiceCommand:
    """
    Голосовая команда с паттернами распознавания.
    """
    name: str
    patterns: List[str]
    handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    description: str = ""
    priority: int = 0


class CommandRegistry:
    """
    Реестр голосовых команд с поддержкой паттернов и приоритетов.
    """

    def __init__(self):
        self.commands: Dict[str, VoiceCommand] = {}
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}

    def register(
        self,
        name: str,
        patterns: List[str],
        handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        description: str = "",
        priority: int = 0
    ) -> None:
        """
        Зарегистрировать голосовую команду.
        
        Args:
            name: имя команды
            patterns: список regex паттернов для распознавания
            handler: async функция обработчик
            description: описание команды
            priority: приоритет (больше = выше)
        """
        command = VoiceCommand(
            name=name,
            patterns=patterns,
            handler=handler,
            description=description,
            priority=priority
        )
        
        self.commands[name] = command
        
        # Компилируем паттерны
        self._compiled_patterns[name] = [
            re.compile(pattern, re.IGNORECASE)
            for pattern in patterns
        ]
        
        logger.info(f"Registered voice command: {name} with {len(patterns)} patterns")

    def get_command(self, name: str) -> Optional[VoiceCommand]:
        """Получить команду по имени."""
        return self.commands.get(name)

    def get_all_commands(self) -> List[VoiceCommand]:
        """Получить все зарегистрированные команды."""
        return list(self.commands.values())

    def match(self, text: str) -> Optional[tuple]:
        """
        Найти команду по тексту.
        
        Args:
            text: распознанный текст
        
        Returns:
            tuple[command_name, extracted_params] или None
        """
        normalized_text = text.strip().lower()
        matches = []
        
        for name, command in self.commands.items():
            patterns = self._compiled_patterns[name]
            
            for pattern in patterns:
                match = pattern.search(normalized_text)
                if match:
                    params = match.groupdict()
                    matches.append((command.priority, name, params))
                    break
        
        if not matches:
            return None
        
        matches.sort(reverse=True, key=lambda x: x[0])
        _, command_name, params = matches[0]
        
        return command_name, params

    async def execute(self, command_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполнить команду.
        
        Args:
            command_name: имя команды
            params: параметры команды
        
        Returns:
            dict: результат выполнения команды
        """
        command = self.commands.get(command_name)
        if not command:
            logger.warning(f"Command not found: {command_name}")
            return {"error": "Command not found"}
        
        try:
            result = await command.handler(params)
            logger.info(f"Executed command: {command_name}")
            return result
        except Exception as e:
            logger.error(f"Error executing command {command_name}: {e}")
            return {"error": str(e)}

"""
Command Matcher - утилиты для сопоставления текста с командами
"""

import logging
from typing import Dict, Any, Optional
from .command_registry import CommandRegistry

logger = logging.getLogger("whisper.command_matcher")


class CommandMatcher:
    """
    Сопоставление распознанного текста с голосовыми командами.
    """

    def __init__(self, registry: CommandRegistry):
        """
        Args:
            registry: реестр команд
        """
        self.registry = registry

    async def process_transcription(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Обработать распознанный текст и выполнить команду если найдена.
        
        Args:
            text: распознанный текст
        
        Returns:
            dict: результат выполнения команды или None
        """
        # Ищем совпадение
        match = self.registry.match(text)
        
        if not match:
            logger.debug(f"No command matched for text: {text}")
            return None
        
        command_name, params = match
        logger.info(f"Matched command: {command_name} with params: {params}")
        
        # Выполняем команду
        result = await self.registry.execute(command_name, params)
        
        return {
            "command": command_name,
            "params": params,
            "result": result
        }

    def get_command_help(self) -> str:
        """
        Получить справку по всем доступным командам.
        
        Returns:
            str: справка в текстовом формате
        """
        commands = self.registry.get_all_commands()
        
        if not commands:
            return "No commands registered"
        
        lines = ["Available voice commands:", ""]
        
        for cmd in sorted(commands, key=lambda c: (-c.priority, c.name)):
            lines.append(f"• {cmd.name}")
            if cmd.description:
                lines.append(f"  {cmd.description}")
            lines.append(f"  Patterns: {len(cmd.patterns)}")
            lines.append("")
        
        return "\n".join(lines)

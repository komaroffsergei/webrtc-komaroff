"""
Command Registry - реестр голосовых команд.
"""

import logging
import re
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass

logger = logging.getLogger("server.voice_commands.registry")


@dataclass
class VoiceCommand:
    name: str
    patterns: List[str]
    handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]
    description: str = ""
    priority: int = 0


class CommandRegistry:
    def __init__(self):
        self.commands: Dict[str, VoiceCommand] = {}
        self._compiled_patterns: Dict[str, List[re.Pattern]] = {}

    def register(
        self,
        name: str,
        patterns: List[str],
        handler: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
        description: str = "",
        priority: int = 0,
    ) -> None:
        command = VoiceCommand(
            name=name,
            patterns=patterns,
            handler=handler,
            description=description,
            priority=priority,
        )

        self.commands[name] = command
        self._compiled_patterns[name] = [re.compile(pattern, re.IGNORECASE) for pattern in patterns]

        logger.info("Registered voice command: %s (%d patterns)", name, len(patterns))

    def get_command(self, name: str) -> Optional[VoiceCommand]:
        return self.commands.get(name)

    def get_all_commands(self) -> List[VoiceCommand]:
        return list(self.commands.values())

    def match(self, text: str) -> Optional[tuple]:
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
        command = self.commands.get(command_name)
        if not command:
            logger.warning("Command not found: %s", command_name)
            return {"error": "Command not found"}

        try:
            result = await command.handler(params)
            logger.info("Executed command: %s", command_name)
            return result
        except Exception as exc:
            logger.error("Error executing command %s: %s", command_name, exc)
            return {"error": str(exc)}

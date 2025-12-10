"""
Command Matcher - сопоставление текста с зарегистрированными голосовыми командами.
"""

import logging
from typing import Dict, Any, Optional
from .command_registry import CommandRegistry

logger = logging.getLogger("server.voice_commands.matcher")


class CommandMatcher:
    def __init__(self, registry: CommandRegistry):
        self.registry = registry

    async def process_transcription(self, text: str) -> Optional[Dict[str, Any]]:
        match = self.registry.match(text)

        if not match:
            logger.debug("No command matched for text: %s", text)
            return None

        command_name, params = match
        logger.info("Matched command: %s with params: %s", command_name, params)

        result = await self.registry.execute(command_name, params)

        return {
            "command": command_name,
            "params": params,
            "result": result,
        }

    def get_command_help(self) -> str:
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

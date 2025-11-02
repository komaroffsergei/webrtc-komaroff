"""
Example Commands - примеры дополнительных команд
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("whisper.commands.examples")


# Команда "reload" - перезагрузить страницу
RELOAD_PATTERNS = [
    r"перезагрузи\s+страницу",
    r"обнови\s+страницу",
    r"reload",
    r"перезагрузка",
]


async def reload_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Обработчик команды reload."""
    logger.info("Reload command triggered")
    return {
        "type": "command",
        "method": "reload",
        "params": {}
    }


# Команда "help" - показать справку
HELP_PATTERNS = [
    r"помощь",
    r"справка",
    r"что\s+ты\s+умеешь",
    r"список\s+команд",
    r"help",
]


async def help_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Обработчик команды help."""
    logger.info("Help command triggered")
    
    help_text = """
    Доступные команды:
    • "Выведи сообщение [текст]" - показать alert
    • "Перезагрузи страницу" - перезагрузить
    • "Помощь" - показать эту справку
    """
    
    return {
        "type": "command",
        "method": "alert",
        "params": {
            "msg": help_text
        }
    }


# Команда "status" - показать статус системы
STATUS_PATTERNS = [
    r"статус",
    r"как\s+дела",
    r"проверка",
    r"status",
]


async def status_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """Обработчик команды status."""
    logger.info("Status command triggered")
    return {
        "type": "message",
        "text": "Система работает нормально",
        "descr": "status"
    }


def register_example_commands(registry):
    """
    Зарегистрировать примеры команд.
    
    Args:
        registry: CommandRegistry
    """
    registry.register(
        name="reload",
        patterns=RELOAD_PATTERNS,
        handler=reload_handler,
        description="Перезагрузить страницу",
        priority=5
    )
    
    registry.register(
        name="help",
        patterns=HELP_PATTERNS,
        handler=help_handler,
        description="Показать справку",
        priority=5
    )
    
    registry.register(
        name="status",
        patterns=STATUS_PATTERNS,
        handler=status_handler,
        description="Показать статус системы",
        priority=5
    )
    
    logger.info("Example commands registered")

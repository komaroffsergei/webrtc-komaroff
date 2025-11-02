"""
Alert Command - команда для отображения сообщений через alert
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("whisper.commands.alert")

# Паттерны для распознавания команды "alert"
ALERT_PATTERNS = [
    r"выведи\s+сообщение\s+(?P<message>.+)",
    r"покажи\s+сообщение\s+(?P<message>.+)",
    r"отобрази\s+сообщение\s+(?P<message>.+)",
    r"покажи\s+алерт\s+(?P<message>.+)",
    r"выведи\s+алерт\s+(?P<message>.+)",
    r"сообщение\s+(?P<message>.+)",
    r"алерт\s+(?P<message>.+)",
]


async def alert_handler(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Обработчик команды alert.
    
    Args:
        params: параметры, извлеченные из распознанного текста
    
    Returns:
        dict: SSE команда для отправки клиенту
    """
    message = params.get("message", "").strip()
    
    if not message:
        logger.warning("Alert command called with empty message")
        return {
            "error": "Empty message"
        }
    
    logger.info(f"Alert command: '{message}'")
    
    # Возвращаем структуру для SSE команды
    return {
        "type": "command",
        "method": "alert",
        "params": {
            "msg": message
        }
    }


def register_alert_command(registry):
    """
    Зарегистрировать команду alert в реестре.
    
    Args:
        registry: CommandRegistry
    """
    registry.register(
        name="alert",
        patterns=ALERT_PATTERNS,
        handler=alert_handler,
        description="Показать alert с сообщением",
        priority=10
    )
    
    logger.info("Alert command registered")

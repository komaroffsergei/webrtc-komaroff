"""
Alert Command - команда для отображения сообщений через alert.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("server.commands.alert")

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
    message = params.get("message", "").strip()

    if not message:
        logger.warning("Alert command called with empty message")
        return {"error": "Empty message"}

    logger.info("Alert command: '%s'", message)

    return {
        "type": "command",
        "method": "alert",
        "params": {"msg": message},
    }


def register_alert_command(registry):
    registry.register(
        name="alert",
        patterns=ALERT_PATTERNS,
        handler=alert_handler,
        description="Показать alert с сообщением",
        priority=10,
    )
    logger.info("Alert command registered")

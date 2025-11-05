"""
Пакет команд для обработки голосовых инструкций на стороне сервера.
"""

from .alert_command import register_alert_command

__all__ = ["register_alert_command"]

"""
Утилиты для регистрации и сопоставления голосовых команд на сервере.
"""

from .command_registry import CommandRegistry
from .command_matcher import CommandMatcher

__all__ = ["CommandRegistry", "CommandMatcher"]

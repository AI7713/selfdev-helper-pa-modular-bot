import re
from typing import Dict, Any, Optional, Callable

class CommandProcessor:
    """
    Обрабатывает внутренние команды агента: /s-check, /вернуться и т.д.
    """
    def __init__(self):
        self.commands: Dict[str, Callable] = {}

    def register(self, cmd_name: str, handler: Callable):
        """Регистрирует обработчик команды"""
        self.commands[cmd_name] = handler

    def process(self, text: str, session_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Если текст — команда, возвращает {'command': ..., 'args': ...}
        Иначе — None
        """
        text = text.strip()
        if not text.startswith('/'):
            return None

        # Поддержка: /команда <аргумент>
        match = re.match(r'^/(\S+)(?:\s+(.+))?$', text)
        if not match:
            return None

        cmd = match.group(1).lower()
        args = match.group(2) if match.group(2) else ""

        return {
            'command': cmd,
            'args': args,
            'handler': self.commands.get(cmd)
        }

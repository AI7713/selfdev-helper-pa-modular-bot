from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

class BaseAgent(ABC):
    """
    Базовый класс для всех агентов.
    Хранит общее состояние сессии и предоставляет интерфейс.
    """
    def __init__(self, user_id: int, agent_name: str):
        self.user_id = user_id
        self.agent_name = agent_name
        self.created_at = datetime.now()
        self.session_data: Dict[str, Any] = {
            'current_block': 'B0',
            'settings': {},
            'experts': [],
            'plan': [],
            'assumptions': [],
            'artifacts': [],
            'state_log': [],
            'completed_blocks': set(),
            'active': True
        }

    @abstractmethod
    async def handle_input(self, update, context, user_input: str):
        """Обработать входное сообщение от пользователя"""
        pass

    @abstractmethod
    async def start_session(self, update, context):
        """Запустить новую сессию агента"""
        pass

    @abstractmethod
    async def finish_session(self, update, context):
        """Завершить сессию и очистить состояние"""
        pass

    def get_current_block(self) -> str:
        return self.session_data['current_block']

    def set_current_block(self, block_id: str):
        self.session_data['current_block'] = block_id
        self.session_data['state_log'].append({
            'block': block_id,
            'timestamp': datetime.now().isoformat()
        })

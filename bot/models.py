"""
Модели данных бота
"""
import time
import hashlib
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timedelta
from collections import OrderedDict
from enum import Enum

class LRUCache:
    """Кэш с алгоритмом LRU (Least Recently Used)"""
    def __init__(self, max_size: int = 1000):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, key: Any) -> Optional[Any]:
        """Получить значение по ключу"""
        if key not in self.cache:
            return None
        self.cache.move_to_end(key)
        return self.cache[key]

    def set(self, key: Any, value: Any):
        """Установить значение по ключу"""
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    def __contains__(self, key: Any) -> bool:
        """Проверка наличия ключа в кэше"""
        return key in self.cache

class RateLimiter:
    """Ограничитель запросов по времени"""
    def __init__(self, max_requests: int = 10, window_seconds: int = 60):
        self.requests = {}
        self.max_requests = max_requests
        self.window = window_seconds

    def is_allowed(self, user_id: int) -> bool:
        """Проверить разрешён ли запрос для пользователя"""
        now = time.time()
        if user_id not in self.requests:
            self.requests[user_id] = []
        user_requests = [req_time for req_time in self.requests[user_id] 
                        if now - req_time < self.window]
        if len(user_requests) < self.max_requests:
            user_requests.append(now)
            self.requests[user_id] = user_requests
            return True
        self.requests[user_id] = user_requests
        return False

class AIResponseCache:
    """Кэш для ответов AI"""
    def __init__(self, max_size: int = 100):
        self.cache = LRUCache(max_size)

    def get_cache_key(self, prompt_key: str, user_query: str) -> str:
        """Сгенерировать ключ кэша"""
        content = f"{prompt_key}:{user_query}"
        return hashlib.md5(content.encode()).hexdigest()

    def get_cached_response(self, prompt_key: str, user_query: str) -> Optional[str]:
        """Получить закэшированный ответ"""
        key = self.get_cache_key(prompt_key, user_query)
        return self.cache.get(key)

    def cache_response(self, prompt_key: str, user_query: str, response: str):
        """Закэшировать ответ"""
        key = self.get_cache_key(prompt_key, user_query)
        self.cache.set(key, response)

class BotState(Enum):
    """Состояния бота"""
    MAIN_MENU = "main_menu"
    BUSINESS_MENU = "business_menu"
    AI_SELECTION = "ai_selection"
    CALCULATOR = "calculator"

class SessionState(Enum):
    """Состояния сессии SKILLTRAINER"""
    INTERVIEW = "interview"
    MODE_SELECTION = "mode_select"
    TRAINING = "training"
    GATE_CHECK = "gate_check"
    FINISH = "finish"

class TrainingMode(Enum):
    """Режимы тренировки SKILLTRAINER"""
    SIM = "sim"
    DRILL = "drill"
    BUILD = "build"
    CASE = "case"
    QUIZ = "quiz"

class SkillSession:
    """Сессия SKILLTRAINER"""
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.state: SessionState = SessionState.INTERVIEW
        self.current_step: int = 0
        self.max_steps: int = 8
        self.answers: Dict[int, str] = {}
        self.selected_mode: Optional[TrainingMode] = None
        self.gates_passed: Set[str] = set()
        self.last_hint: Optional[str] = None
        self.created_at: datetime = datetime.now()
        self.progress: float = 0.0
        self.finish_packet: Optional[str] = None
        self.training_complete: bool = False

    def update_progress(self):
        """Обновить прогресс сессии"""
        self.progress = min(1.0, (self.current_step + 1) / self.max_steps)

    def add_answer(self, step: int, answer: str):
        """Добавить ответ на вопрос"""
        self.answers[step] = answer
        self.current_step = step + 1
        self.update_progress()

    def pass_gate(self, gate_id: str):
        """Отметить пройденный гейт"""
        self.gates_passed.add(gate_id)

    def set_hint(self, hint: str):
        """Установить подсказку"""
        if len(hint) <= 240:
            self.last_hint = hint

    def is_gate_passed(self, gate_id: str) -> bool:
        """Проверить пройден ли гейт"""
        return gate_id in self.gates_passed

# ==============================================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ==============================================================================
# Глобальные экземпляры для использования во всём приложении
user_stats_cache = LRUCache(max_size=500)
rate_limiter = RateLimiter(max_requests=15, window_seconds=60)
ai_cache = AIResponseCache(max_size=100)
active_skill_sessions: Dict[int, SkillSession] = {}

# Новый кэш истории с TTL = 1 час
# Формат: {user_id: {"history": [{"role": "...", "content": "..."}], "last_activity": datetime}}
user_conversation_history: Dict[int, Dict[str, Any]] = {}

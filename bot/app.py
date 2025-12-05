"""
Основной модуль инициализации бота
"""
import asyncio
import os

from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram.constants import ParseMode
from groq import Groq

from .config import (
    TELEGRAM_TOKEN, GROQ_API_KEY, PORT, WEBHOOK_URL,
    logger, BOT_VERSION
)
from .models import (
    LRUCache, RateLimiter, AIResponseCache,
    BotState, user_stats_cache, rate_limiter, ai_cache, active_skill_sessions
)
from .handlers.commands import setup_commands
from .handlers.calculator import setup_calculator_handlers
from .handlers.skilltrainer import setup_skilltrainer_handlers
from .handlers.ai_handlers import setup_ai_handlers
from .handlers.main_handler import setup_main_handler
from .web.server import setup_web_server


# Инициализация Groq клиента
groq_client: Groq | None = None
if GROQ_API_KEY:
    try:
        groq_client = Groq(api_key=GROQ_API_KEY)
        logger.info("Groq client initialized successfully")
    except Exception as e:
        logger.error(f"Ошибка инициализации Groq клиента: {type(e).__name__}")
else:
    logger.warning("GROQ_API_KEY не установлен. Функции AI будут недоступны.")

# Сохраняем groq_client глобально для использования в обработчиках
GLOBAL_GROQ_CLIENT = groq_client


def create_application() -> Application:
    """
    Создание и настройка приложения Telegram бота
    
    Returns:
        Настроенное приложение
    """
    # Используем глобальный groq_client
    global GLOBAL_GROQ_CLIENT
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен. Запуск невозможен.")
        raise ValueError("TELEGRAM_TOKEN не установлен")
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # Настраиваем обработчики команд
    setup_commands(application)
    
    # Настраиваем обработчики калькулятора
    setup_calculator_handlers(application)
    
    # Настраиваем обработчики SKILLTRAINER
    setup_skilltrainer_handlers(application)
    
    # Настраиваем обработчики AI
    setup_ai_handlers(application, GLOBAL_GROQ_CLIENT)
    
    # Настраиваем основной обработчик текстовых сообщений
    setup_main_handler(application)
    
    logger.info(f"{BOT_VERSION} - Приложение создано и настроено")
    return application

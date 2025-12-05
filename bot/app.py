"""
Основной модуль инициализации бота
"""
import asyncio
import os

from telegram.ext import Application
from groq import Groq

from .config import (
    TELEGRAM_TOKEN, GROQ_API_KEY, PORT, WEBHOOK_URL,
    logger, BOT_VERSION
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


def create_application() -> Application:
    """
    Создание и настройка приложения Telegram бота
    
    Returns:
        Настроенное приложение
    """
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен. Запуск невозможен.")
        raise ValueError("TELEGRAM_TOKEN не установлен")
    
    # Создаем приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # ✅ Храним groq_client в bot_data — правильное место для глобальных данных
    application.bot_data['groq_client'] = groq_client

    # Настраиваем обработчики команд
    setup_commands(application)
    
    # Настраиваем обработчики калькулятора
    setup_calculator_handlers(application)
    
    # Настраиваем обработчики SKILLTRAINER
    setup_skilltrainer_handlers(application)
    
    # Настраиваем обработчики AI — БЕЗ передачи groq_client
    setup_ai_handlers(application)
    
    # Настраиваем основной обработчик текстовых сообщений
    setup_main_handler(application)
    
    logger.info(f"{BOT_VERSION} - Приложение создано и настроено")
    return application


async def run_polling():
    """
    Запуск бота в режиме polling (для локальной разработки)
    """
    application = create_application()
    logger.info(f"{BOT_VERSION} - Запуск в режиме polling...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Бесконечный цикл
    await asyncio.Future()


async def run_webhook():
    """
    Запуск бота в режиме webhook (для продакшена на Render)
    """
    if not WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL не установлен. Webhook режим невозможен.")
        return
    
    application = create_application()
    
    # Настраиваем и запускаем web сервер
    await setup_web_server(application, PORT, WEBHOOK_URL)


def run_bot():
    """
    Основная функция запуска бота
    
    Определяет режим запуска на основе переменных окружения:
    - Если есть WEBHOOK_URL и PORT → webhook режим (для Render)
    - Иначе → polling режим (для локальной разработки)
    """
    logger.info(f"{BOT_VERSION} - Starting bot with SKILLTRAINER and security improvements...")
    
    # Проверка необходимых переменных окружения
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен. Запуск невозможен.")
        return
    
    # Определяем режим запуска
    if WEBHOOK_URL and PORT:
        logger.info(f"{BOT_VERSION} - Запуск в режиме webhook (Render)")
        asyncio.run(run_webhook())
    else:
        logger.info(f"{BOT_VERSION} - Запуск в режиме polling (локальная разработка)")
        asyncio.run(run_polling())

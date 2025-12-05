"""
Основной модуль инициализации бота (модульная версия, совместимая с v3.3.5)
"""
import asyncio
import os

from telegram.ext import Application, CallbackQueryHandler
from groq import Groq

from .config import (
    TELEGRAM_TOKEN, GROQ_API_KEY, PORT, WEBHOOK_URL,
    logger, BOT_VERSION
)
from .handlers.commands import (
    setup_commands,
    show_main_menu  # ← глобальный обработчик главного меню
)
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
    """
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен. Запуск невозможен.")
        raise ValueError("TELEGRAM_TOKEN не установлен")
    
    # Создаём приложение
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    
    # ✅ Сохраняем groq_client в bot_data — доступен глобально
    application.bot_data['groq_client'] = groq_client

    # Основные команды
    setup_commands(application)

    # 🔹 ГЛОБАЛЬНАЯ РЕГИСТРАЦИЯ: кнопка "В главное меню" работает везде
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^main_menu$'))

    # Остальные обработчики
    setup_calculator_handlers(application)
    setup_skilltrainer_handlers(application)
    setup_ai_handlers(application)  # ← без groq_client
    setup_main_handler(application)
    
    logger.info(f"{BOT_VERSION} - Приложение создано и настроено")
    return application


async def run_polling():
    """
    Запуск бота в режиме polling (для локальной разработки)
    """
    application = create_application()
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info(f"{BOT_VERSION} - Запуск в режиме polling...")
    await asyncio.Future()


async def run_webhook():
    """
    Запуск бота в режиме webhook (для Render)
    """
    if not WEBHOOK_URL:
        logger.error("❌ WEBHOOK_URL не установлен. Webhook режим невозможен.")
        return
    
    application = create_application()
    await setup_web_server(application, PORT, WEBHOOK_URL)


def run_bot():
    """
    Основная функция запуска бота
    """
    logger.info(f"{BOT_VERSION} - Starting bot with SKILLTRAINER and security improvements...")
    
    if not TELEGRAM_TOKEN:
        logger.error("❌ TELEGRAM_TOKEN не установлен. Запуск невозможен.")
        return
    
    if WEBHOOK_URL and PORT:
        logger.info(f"{BOT_VERSION} - Запуск в режиме webhook (Render)")
        asyncio.run(run_webhook())
    else:
        logger.info(f"{BOT_VERSION} - Запуск в режиме polling (локальная разработка)")
        asyncio.run(run_polling())

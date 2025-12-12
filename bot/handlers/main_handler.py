"""Главный обработчик текстовых сообщений и маршрутизация (с TTL = 1 час для кэша истории)"""
from telegram import Update
from telegram.ext import ContextTypes, Application, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from datetime import datetime, timedelta
from ..config import logger
from ..models import BotState, active_skill_sessions, user_conversation_history
from .commands import show_usage_progress  # ← ИМПОРТИРУЕМ ТОЛЬКО ЭТО


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """Главный обработчик текстовых сообщений"""
    user_text = update.message.text.strip()
    user_id = update.message.from_user.id

    # === ПРОВЕРКА TTL = 1 ЧАС ===
    if user_id in user_conversation_history:
        last_activity = user_conversation_history[user_id]["last_activity"]
        if datetime.now() - last_activity > timedelta(hours=1):
            del user_conversation_history[user_id]
        else:
            user_conversation_history[user_id]["last_activity"] = datetime.now()

    # Обработка кнопок reply-клавиатуры
    if user_text == "🏠 Меню":
        from .commands import start
        return await start(update, context)
    if user_text == "📊 Прогресс":
        await show_usage_progress(update, context)
        return context.user_data.get('state', BotState.MAIN_MENU)

    # Проверка активной сессии SKILLTRAINER
    if user_id in active_skill_sessions:
        from .skilltrainer import handle_skilltrainer_response
        session = active_skill_sessions[user_id]
        await handle_skilltrainer_response(update, context, session)
        return context.user_data.get('state', BotState.MAIN_MENU)

    # Обработка специальных команд в тексте
    if any(word in user_text.lower() for word in ['пригласи', 'друг', 'реферал', 'ссылка']):
        from .commands import show_referral_program
        await show_referral_program(update, context)
        return BotState.MAIN_MENU

    if any(word in user_text.lower() for word in ['прогресс', 'статистика', 'стата']):
        await show_usage_progress(update, context)
        return BotState.MAIN_MENU

    # Получаем текущее состояние бота
    current_state = context.user_data.get('state', BotState.MAIN_MENU)

    # Маршрутизация по состояниям
    if current_state == BotState.CALCULATOR:
        from .calculator import handle_economy_calculator
        await handle_economy_calculator(update, context)
        return BotState.CALCULATOR
    elif context.user_data.get('active_groq_mode'):
        active_mode = context.user_data['active_groq_mode']
        from .ai_handlers import handle_groq_request
        await handle_groq_request(update, context, active_mode)
        return BotState.AI_SELECTION
    elif current_state in (BotState.AI_SELECTION, BotState.BUSINESS_MENU):
        await update.message.reply_text(
            "❓ Вы отправили текст, но не активировали ни один из ИИ-инструментов. "
            "Нажмите на кнопку 'Активировать' под нужным инструментом, чтобы начать диалог, "
            "или 🏠 Меню для возврата."
        )
        return current_state
    else:
        # Помощь по умолчанию
        from ..config import BOT_VERSION
        help_text = f"""🤖 **Personal Growth AI** {BOT_VERSION}
💡 **Доступные команды:**
/start - Главное меню
/progress - Ваш прогресс и статистика

🎯 **Быстрый старт:**
• Напишите "пригласи друга" для реферальной программы
• Используйте "мой прогресс" для статистики
• Выберите инструмент из меню

🚀 **Новый инструмент: SKILLTRAINER**
Многошаговая сессия развития навыков с гейтами и прогресс-баром!"""
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)
        return current_state


def setup_main_handler(application: Application):
    """Настройка главного обработчика текстовых сообщений"""
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    
    # РЕГИСТРИРУЕМ КНОПКУ «📊 Мой прогресс» — используем СУЩЕСТВУЮЩУЮ функцию
    application.add_handler(CallbackQueryHandler(show_usage_progress, pattern='^show_progress$'))
    
    logger.info("Главный обработчик сообщений настроен")

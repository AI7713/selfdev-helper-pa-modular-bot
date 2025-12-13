"""Главный обработчик текстовых сообщений и маршрутизация (с TTL = 1 час для кэша истории)"""
from telegram import Update
from telegram.ext import ContextTypes, Application, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode
from datetime import datetime, timedelta
from ..config import logger
from ..models import BotState, active_skill_sessions, user_conversation_history
from .commands import show_usage_progress


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

    # 🔧 Проверка активного UAF-агента (например, Оркестратор)
    active_agent = context.user_data.get('active_agent')
    if active_agent and hasattr(active_agent, 'handle_input'):
        await active_agent.handle_input(update, context, user_text)
        return context.user_data.get('state', BotState.AI_SELECTION)

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


async def handle_orchestrator_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка нажатий кнопок Оркестратора: orch_action:..., orch_cmd:..."""
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    user_id = query.from_user.id

    active_agent = context.user_data.get('active_agent')
    if not active_agent or not hasattr(active_agent, 'session_data'):
        await query.message.reply_text("⚠️ Сессия не активна. Запустите Оркестратор заново.")
        return

    # Обработка действий
    if callback_data.startswith("orch_action:"):
        action = callback_data.split(":", 1)[1]
        if action == "go_to_B1a":
            active_agent.session_data['current_block'] = 'B1.a'
            await query.message.reply_text("🔍 Отлично! Теперь уточним детали:\n• Целевая аудитория (ЦА)\n• Сроки\n• Ограничения (бюджет, каналы и т.д.)")
        elif action == "confirm_B1b":
            active_agent.session_data['current_block'] = 'B1.c'
            await query.message.reply_text("✅ Формулировка подтверждена. Переходим к настройкам...")
        elif action == "refine_ca":
            await query.message.reply_text("✏️ Уточните целевую аудиторию и JTBD (работу, которую она хочет выполнить):")
        elif action == "show_preflight":
            preflight = (
                "📊 **Mini Pre-flight** (пример):\n"
                "• Бюджет: min 50k / base 100k / max 200k ₽\n"
                "• Ресурсы: PM, Data, FinOps (10–15 ч/нед)\n"
                "• Данные: PII — жёлтый, доступы — есть\n"
                "• Допущения: ЦА — предприниматели 25–45 лет\n"
                "• Риски: зависимость от одного поставщика\n"
                "• Метрики: North Star — LTV, Lead — конверсия"
            )
            await query.message.reply_text(preflight, parse_mode=ParseMode.MARKDOWN)
        else:
            await query.message.reply_text(f"🛠️ Действие `{action}` получено.")

    # Обработка команд через кнопки
    elif callback_data.startswith("orch_cmd:"):
        cmd = callback_data.split(":", 1)[1]
        if cmd == "s-check":
            await query.message.reply_text("🔍 Запускаю S-CHECK (Self-Critique)...")
            # Здесь будет вызов LLM с шаблоном S-CHECK
        else:
            await query.message.reply_text(f"⚙️ Команда `{cmd}` — в обработке.")


def setup_main_handler(application: Application):
    """Настройка главного обработчика текстовых сообщений"""
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    # РЕГИСТРИРУЕМ КНОПКУ «📊 Мой прогресс»
    application.add_handler(CallbackQueryHandler(show_usage_progress, pattern='^show_progress$'))
    # 🔧 РЕГИСТРИРУЕМ КНОПКИ ОРКЕСТРАТОРА
    application.add_handler(CallbackQueryHandler(handle_orchestrator_callback, pattern=r'^orch_(action|cmd):.+'))
    logger.info("Главный обработчик сообщений настроен")

"""
Обработчики команд бота (/start, /menu, /progress, /version, /referral, /clear_history)
"""
import os
from typing import Dict, Any
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode
from ..config import (
    logger, BOT_VERSION, CONFIG_VERSION, SKILLTRAINER_VERSION,
    DEMO_SCENARIOS, SYSTEM_PROMPTS, REPLY_KEYBOARD_MARKUP
)
from ..models import user_stats_cache, active_skill_sessions, BotState, user_conversation_history
from ..utils import split_message_efficiently


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

async def get_usage_stats(user_id: int) -> Dict[str, Any]:
    """
    Получение статистики использования пользователя
    """
    if user_id not in user_stats_cache:
        user_stats_cache.set(user_id, {
            'tools_used': 0,
            'ai_requests': 0,
            'calculator_uses': 0,
            'skilltrainer_sessions': 0,
            'first_seen': datetime.now().strftime('%Y-%m-%d'),
            'last_active': datetime.now().strftime('%Y-%m-%d'),
            'ab_test_group': 'A' if user_id % 2 == 0 else 'B'
        })
    stats = user_stats_cache.get(user_id)
    stats['last_active'] = datetime.now().strftime('%Y-%m-%d')
    user_stats_cache.set(user_id, stats)
    return stats


async def update_usage_stats(user_id: int, tool_type: str):
    """
    Обновление статистики использования
    """
    stats = await get_usage_stats(user_id)
    if tool_type == 'ai':
        stats['ai_requests'] += 1
    elif tool_type == 'calculator':
        stats['calculator_uses'] += 1
    elif tool_type == 'skilltrainer':
        stats['skilltrainer_sessions'] = stats.get('skilltrainer_sessions', 0) + 1
    tools_used = set()
    if stats['ai_requests'] > 0:
        tools_used.add('ai')
    if stats['calculator_uses'] > 0:
        tools_used.add('calculator')
    if stats.get('skilltrainer_sessions', 0) > 0:
        tools_used.add('skilltrainer')
    stats['tools_used'] = len(tools_used)
    stats['last_tool'] = tool_type
    user_stats_cache.set(user_id, stats)


async def show_usage_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показать прогресс использования бота (работает и с callback, и с message)
    """
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    elif update.message:
        user_id = update.message.from_user.id
    else:
        logger.warning("show_usage_progress: невозможно определить пользователя")
        return

    stats = await get_usage_stats(user_id)
    tools_progress = "▰" * min(stats['tools_used'], 5) + "▱" * (5 - min(stats['tools_used'], 5))
    ai_progress = "▰" * min(stats['ai_requests'] // 3, 5) + "▱" * (5 - min(stats['ai_requests'] // 3, 5))
    
    progress_text = f"""
📊 **ВАШ ПРОГРЕСС:**
🛠️ Инструменты: {tools_progress} {stats['tools_used']}/5
🤖 AI запросы: {ai_progress} {stats['ai_requests']}+
📈 Калькулятор: {stats['calculator_uses']} использований
🎓 SKILLTRAINER: {stats.get('skilltrainer_sessions', 0)} сессий
🎯 Группа теста: {stats['ab_test_group']}
💡 Исследуйте больше инструментов для увеличения прогресса!
    """
    
    if update.callback_query:
        await update.callback_query.message.reply_text(progress_text, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(progress_text, parse_mode=ParseMode.MARKDOWN)


async def get_personal_recommendation(user_id: int) -> str:
    """
    Получить персональную рекомендацию для пользователя
    """
    stats = await get_usage_stats(user_id)
    if stats['calculator_uses'] > stats['ai_requests']:
        return "🎯 **Вам подойдет:** Аналитик + Маркетолог (для углубления анализа)"
    elif stats['ai_requests'] > 5:
        return "🎯 **Попробуйте:** Калькулятор для точных финансовых расчетов"
    elif stats.get('skilltrainer_sessions', 0) == 0:
        return "🎯 **Попробуйте:** SKILLTRAINER для структурированного развития навыков"
    else:
        return "🎯 **Начните с:** Быстрый старт в меню 'Для себя'"


async def show_referral_program(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Показать реферальную программу
    """
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    elif update.message:
        user_id = update.message.from_user.id
    else:
        return

    bot_username = (await context.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
    referral_text = f"""
🎁 **ПРИГЛАСИ ДРУЗЕЙ - ПОЛУЧИ БОНУСЫ!**
Пригласи друга по ссылке:
`{ref_link}`
За каждого друга:
✅ +5 дополнительных AI запросов
✅ Расширенная статистика
✅ Специальные возможности
💬 Просто отправь другу эту ссылку!
    """
    
    if update.callback_query:
        await update.callback_query.message.reply_text(referral_text, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(referral_text, parse_mode=ParseMode.MARKDOWN)


# ==============================================================================
# ОСНОВНЫЕ КОМАНДЫ
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик команды /start — главное меню (Вариант 1: Три колонны)
    """
    if not update.message:
        return BotState.MAIN_MENU
    
    user_id = update.message.from_user.id

    # === ОЧИСТКА ИСТОРИИ ПРИ /START ===
    if user_id in user_conversation_history:
        del user_conversation_history[user_id]

    if user_id in active_skill_sessions:
        del active_skill_sessions[user_id]
    
    stats = await get_usage_stats(user_id)
    
    # Отправляем нижнюю клавиатуру
    await update.message.reply_text("👋 Привет! Используйте нижнюю панель для навигации.", reply_markup=REPLY_KEYBOARD_MARKUP)
    
    # Показываем прогресс, если есть
    if stats['tools_used'] > 0:
        await show_usage_progress(update, context)
    
    # Главное меню: Три колонны
    keyboard = [
        [
            InlineKeyboardButton("🧠 Мудрец", callback_data='ai_sage_self'),
            InlineKeyboardButton("📈 Стратег", callback_data='ai_strategist_self'),
            InlineKeyboardButton("🧭 Наставник", callback_data='ai_mentor_self')
        ],
        [
            InlineKeyboardButton("💡 Идеатор", callback_data='ai_ideator_self'),
            InlineKeyboardButton("✨ Редактор", callback_data='ai_editor_self'),
            InlineKeyboardButton("📈 Рост-эксперт", callback_data='ai_growth_expert_self')
        ],
        [
            InlineKeyboardButton("💼 HR-советник", callback_data='ai_hr_advisor_self'),
            InlineKeyboardButton("🤝 Посредник", callback_data='ai_mediator_self'),
            InlineKeyboardButton("🌟 Фраза дня", callback_data='ai_daily_phrase_self')
        ],
        [
            InlineKeyboardButton("🔮 Гороскоп разума", callback_data='ai_mind_horoscope_self'),
            InlineKeyboardButton("🌙 Рефлексия дня", callback_data='ai_daily_reflection_self')
        ],
        [
            InlineKeyboardButton("💡 ПРОФИ", callback_data='profi_section'),
            InlineKeyboardButton("🎓 ПРОГРАММЫ", callback_data='programs_section')
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    welcome_text = (
        "👋 Это ваш личный AI-тренер и стратег.\n"
        "Выберите формат:\n"
        "• Бесплатные инструменты — для старта,\n"
        "• Платные промты — для глубокого анализа,\n"
        "• Программы — для реальных результатов."
    )
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    context.user_data['state'] = BotState.MAIN_MENU
    context.user_data['active_groq_mode'] = None
    
    logger.info(f"{BOT_VERSION} - User {user_id} started bot (Group: {stats['ab_test_group']})")
    return BotState.MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    return await start(update, context)


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    version_info = f"""
🤖 **Personal Growth AI** {BOT_VERSION}
📊 **КОМПОНЕНТЫ:**
• Архитектура: {BOT_VERSION} (Гибридный бот + Growth + SKILLTRAINER)
• Конфигурация: {CONFIG_VERSION}
• Калькулятор: v1.0 (полный из первого бота)
• AI движок: v2.0 (Groq + 9 инструментов + кэширование)
• SKILLTRAINER: {SKILLTRAINER_VERSION} (полная реализация)
🔄 **ЧТО ВКЛЮЧЕНО:**
✅ Детальный калькулятор маркетплейса (6 шагов)
✅ 9 AI-инструментов с системными промтами (включая SKILLTRAINER)
✅ SKILLTRAINER: 7 шагов диагностики + 5 режимов + гейты + HUD
✅ Разбивка длинных ответов (>4096 символов)
✅ Growth фичи (A/B тесты, прогресс-бар, виральность)
✅ Inline + Reply навигация
✅ Webhook для Render
✅ Rate limiting и кэширование
✅ Защита от инъекций
💡 Используйте /progress для вашей статистики
"""
    await update.message.reply_text(version_info, parse_mode=ParseMode.MARKDOWN)


async def progress_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_usage_progress(update, context)
    user_id = update.message.from_user.id
    recommendation = await get_personal_recommendation(user_id)
    await update.message.reply_text(recommendation, parse_mode=ParseMode.MARKDOWN)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_referral_program(update, context)


# ==============================================================================
# КОМАНДА /clear_history
# ==============================================================================

async def clear_history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Очистить историю разговора"""
    user_id = update.message.from_user.id
    if user_id in user_conversation_history:
        del user_conversation_history[user_id]
        await update.message.reply_text("✅ История разговора очищена.")
    else:
        await update.message.reply_text("ℹ️ История разговора пуста.")


# ==============================================================================
# ГЛАВНОЕ МЕНЮ ЧЕРЕЗ CALLBACK
# ==============================================================================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик кнопки «В главное меню» (работает из callback)
    """
    query = update.callback_query
    if query:
        await query.answer()
        user_id = query.from_user.id

        # === ОЧИСТКА ИСТОРИИ НЕ НУЖНА — ПОТОМУ ЧТО /START УЖЕ ОЧИЩАЕТ ===

        stats = await get_usage_stats(user_id)
        
        keyboard = [
            [
                InlineKeyboardButton("🧠 Мудрец", callback_data='ai_sage_self'),
                InlineKeyboardButton("📈 Стратег", callback_data='ai_strategist_self'),
                InlineKeyboardButton("🧭 Наставник", callback_data='ai_mentor_self')
            ],
            [
                InlineKeyboardButton("💡 Идеатор", callback_data='ai_ideator_self'),
                InlineKeyboardButton("✨ Редактор", callback_data='ai_editor_self'),
                InlineKeyboardButton("📈 Рост-эксперт", callback_data='ai_growth_expert_self')
            ],
            [
                InlineKeyboardButton("💼 HR-советник", callback_data='ai_hr_advisor_self'),
                InlineKeyboardButton("🤝 Посредник", callback_data='ai_mediator_self'),
                InlineKeyboardButton("🌟 Фраза дня", callback_data='ai_daily_phrase_self')
            ],
            [
                InlineKeyboardButton("🔮 Гороскоп разума", callback_data='ai_mind_horoscope_self'),
                InlineKeyboardButton("🌙 Рефлексия дня", callback_data='ai_daily_reflection_self')
            ],
            [
                InlineKeyboardButton("💡 ПРОФИ", callback_data='profi_section'),
                InlineKeyboardButton("🎓 ПРОГРАММЫ", callback_data='programs_section')
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        welcome_text = (
            "👋 Это ваш личный AI-тренер и стратег.\n"
            "Выберите формат:\n"
            "• Бесплатные инструменты — для старта,\n"
            "• Платные промты — для глубокого анализа,\n"
            "• Программы — для реальных результатов."
        )
        
        await query.edit_message_text(welcome_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        context.user_data['state'] = BotState.MAIN_MENU
        context.user_data['active_groq_mode'] = None
        return BotState.MAIN_MENU
    else:
        return await start(update, context)


# ==============================================================================
# ОБРАБОТЧИКИ ДЛЯ ПРОФИ И ПРОГРАММ (заглушки)
# ==============================================================================

async def profi_section_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🎓 SKILLTRAINER", callback_data='ai_skilltrainer_business')],
        [InlineKeyboardButton("📊 Калькулятор маркетплейсов", callback_data='menu_calculator')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "💡 **ПРОФИ** (ограничено)\n"
        "• SKILLTRAINER — многошаговая тренировка навыков\n"
        "• Калькулятор маркетплейсов — финансовый анализ\n"
        "Лимит: 3 запроса в день.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return BotState.MAIN_MENU


async def programs_section_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🎓 **ПРОГРАММЫ** (скоро)\n"
        "Готовые маршруты к результату:\n"
        "• Мастер переговоров\n"
        "• Бизнес-инженер\n"
        "• Лидер будущего\n\n"
        "Следите за обновлениями!",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    return BotState.MAIN_MENU


# ==============================================================================
# НАСТРОЙКА ОБРАБОТЧИКОВ
# ==============================================================================

def setup_commands(application: Application):
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("version", version_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("referral", referral_command))
    application.add_handler(CommandHandler("clear_history", clear_history_command))  # ← новая команда
    
    # Новые обработчики для разделов
    application.add_handler(CallbackQueryHandler(profi_section_handler, pattern='^profi_section$'))
    application.add_handler(CallbackQueryHandler(programs_section_handler, pattern='^programs_section$'))
    
    logger.info("Командные обработчики настроены")

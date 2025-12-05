"""
Обработчики команд бота (/start, /menu, /progress, /version, /referral)
"""
import os
from typing import Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes, Application, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from ..config import (
    logger, BOT_VERSION, CONFIG_VERSION, SKILLTRAINER_VERSION,
    REPLY_KEYBOARD_MARKUP, DEMO_SCENARIOS, SYSTEM_PROMPTS
)
from ..models import user_stats_cache, active_skill_sessions, BotState
from ..utils import split_message_efficiently


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

async def get_usage_stats(user_id: int) -> Dict[str, Any]:
    """
    Получение статистики использования пользователя
    """
    if user_id not in user_stats_cache:
        from datetime import datetime
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
    # Определяем user_id из любого источника
    if update.callback_query:
        user_id = update.callback_query.from_user.id
    elif update.message:
        user_id = update.message.from_user.id
    else:
        logger.warning("show_usage_progress: невозможно определить пользователя")
        return

    stats = await get_usage_stats(user_id)
    
    # Создаем прогресс-бары
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
    
    # Отправляем в зависимости от контекста
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
    Обработчик команды /start
    """
    if not update.message:
        return BotState.MAIN_MENU
    
    user_id = update.message.from_user.id
    
    # Очищаем активные сессии если есть
    if user_id in active_skill_sessions:
        del active_skill_sessions[user_id]
    
    # Получаем статистику
    stats = await get_usage_stats(user_id)
    
    # Создаем клавиатуру в зависимости от группы A/B теста
    if stats['ab_test_group'] == 'A':
        inline_keyboard = [
            [InlineKeyboardButton("Для себя (ИИ-инструменты)", callback_data='menu_self')],
            [InlineKeyboardButton("Для дела (Калькуляторы и ИИ-инструменты)", callback_data='menu_business')]
        ]
        welcome_text = "👋 Привет! Выберите инструмент:"
    else:
        inline_keyboard = [
            [InlineKeyboardButton("🧠 Личный рост", callback_data='menu_self')],
            [InlineKeyboardButton("🚀 Бизнес и карьера", callback_data='menu_business')],
            [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')]
        ]
        welcome_text = f"🎯 Добро пожаловать! Ваша группа: {stats['ab_test_group']}\nВыберите направление:"
    
    inline_markup = InlineKeyboardMarkup(inline_keyboard)
    
    # Отправляем reply-клавиатуру
    reply_keyboard = ReplyKeyboardMarkup(
        [[KeyboardButton("🏠 Меню"), KeyboardButton("📊 Прогресс")]],
        one_time_keyboard=False,
        resize_keyboard=True
    )
    
    await update.message.reply_text("👋 Привет! Используйте нижнюю панель для навигации.", reply_markup=reply_keyboard)
    
    # Показываем прогресс если пользователь уже использовал инструменты
    if stats['tools_used'] > 0:
        await show_usage_progress(update, context)
    
    # Отправляем основное меню
    await update.message.reply_text(welcome_text, reply_markup=inline_markup)
    
    # Устанавливаем состояние
    context.user_data['state'] = BotState.MAIN_MENU
    context.user_data['active_groq_mode'] = None
    
    logger.info(f"{BOT_VERSION} - User {user_id} started bot (Group: {stats['ab_test_group']})")
    return BotState.MAIN_MENU


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик команды /menu
    """
    return await start(update, context)


async def version_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /version
    """
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
    """
    Обработчик команды /progress
    """
    await show_usage_progress(update, context)
    
    user_id = update.message.from_user.id
    recommendation = await get_personal_recommendation(user_id)
    await update.message.reply_text(recommendation, parse_mode=ParseMode.MARKDOWN)


async def referral_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /referral
    """
    await show_referral_program(update, context)


# ==============================================================================
# ФУНКЦИЯ ДЛЯ МЕНЮ
# ==============================================================================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Показать главное меню (используется из ai_handlers)
    """
    return await start(update, context)


# ==============================================================================
# НАСТРОЙКА ОБРАБОТЧИКОВ
# ==============================================================================

def setup_commands(application: Application):
    """
    Настройка обработчиков команд для приложения
    """
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("version", version_command))
    application.add_handler(CommandHandler("progress", progress_command))
    application.add_handler(CommandHandler("referral", referral_command))
    
    logger.info("Командные обработчики настроены")

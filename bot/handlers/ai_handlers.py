"""
Обработчики AI запросов к Groq API (исправленная версия для нового главного меню)
"""
import asyncio
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CallbackQueryHandler
from telegram.constants import ParseMode
from groq import Groq, APIError
from ..config import (
    logger, SYSTEM_PROMPTS, DEMO_SCENARIOS
)
from ..models import rate_limiter, ai_cache, BotState
from ..utils import sanitize_user_input, split_message_efficiently
from .commands import update_usage_stats


# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================

async def send_long_message(chat_id: int, text: str, context: ContextTypes.DEFAULT_TYPE,
                          prefix: str = "", parse_mode: str = None):
    parts = split_message_efficiently(text)
    total_parts = len(parts)
    for i, part in enumerate(parts, 1):
        part_prefix = prefix if total_parts == 1 else f"{prefix}*({i}/{total_parts})*\n"
        await context.bot.send_message(chat_id, f"{part_prefix}{part}", parse_mode=parse_mode)


async def handle_groq_request(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_key: str):
    groq_client: Optional[Groq] = context.application.bot_data.get('groq_client')
    if not groq_client:
        await update.message.reply_text("❌ AI функции временно недоступны. Попробуйте позже.")
        return
    if not update.message:
        return
    user_id = update.message.from_user.id
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("🚫 Слишком много запросов. Подождите минуту.")
        return
    user_query = sanitize_user_input(update.message.text)
    system_prompt = SYSTEM_PROMPTS.get(prompt_key, "Вы — полезный ассистент.")
    await update.message.chat.send_message(
        f"⌛ **{prompt_key.capitalize()}** обрабатывает ваш запрос...",
        parse_mode=ParseMode.MARKDOWN
    )
    try:
        cached_response = ai_cache.get_cached_response(prompt_key, user_query)
        if cached_response:
            await send_long_message(
                update.message.chat.id,
                cached_response,
                context,
                prefix=f"🤖 Ответ {prompt_key.capitalize()} (из кэша):\n",
                parse_mode=None
            )
            await update_usage_stats(user_id, 'ai')
            return
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=4000
        )
        ai_response = chat_completion.choices[0].message.content
        ai_cache.cache_response(prompt_key, user_query, ai_response)
        await send_long_message(
            update.message.chat.id,
            ai_response,
            context,
            prefix=f"🤖 Ответ {prompt_key.capitalize()}:\n",
            parse_mode=None
        )
        await update_usage_stats(user_id, 'ai')
    except APIError as e:
        logger.error(f"ОШИБКА GROQ API: {e}")
        if e.status_code == 429:
            user_message = "❌ **Превышен лимит запросов.** Подождите минуту."
        elif e.status_code == 400:
            user_message = "❌ **Ошибка 400: Неверный запрос или лимиты.**"
        elif e.status_code == 401:
            user_message = "❌ **Ошибка 401: Неверный API ключ.**"
        else:
            user_message = f"❌ **Ошибка Groq API:** Код {e.status_code}"
        await update.message.chat.send_message(user_message, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"Неизвестная ошибка: {e}")
        await update.message.chat.send_message(
            "Произошла ошибка при обращении к AI.",
            parse_mode=ParseMode.MARKDOWN
        )


# ==============================================================================
# ОБРАБОТЧИКИ МЕНЮ И ВЫБОРА AI ИНСТРУМЕНТОВ
# ==============================================================================

async def show_demo_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    demo_key = query.data.split('_')[1]
    text_content = DEMO_SCENARIOS.get(demo_key, "⚠️ Описание демо-сценария не найдено.")
    # ВСЕГДА возвращаем в главное меню
    keyboard = [[InlineKeyboardButton("🔙 Назад к выбору AI", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text_content, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    context.user_data['state'] = BotState.AI_SELECTION
    return BotState.AI_SELECTION


def get_ai_keyboard(prompt_key: str) -> InlineKeyboardMarkup:
    """Упрощённая клавиатура: «Назад» ведёт только в главное меню"""
    keyboard = [
        [InlineKeyboardButton("💡 Демо-сценарий (что он умеет?)", callback_data=f'demo_{prompt_key}')],
        [InlineKeyboardButton("✅ Активировать", callback_data=f'activate_{prompt_key}')],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)


async def ai_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    callback_data = query.data
    prompt_key = callback_data.split('_')[1]
    context.user_data['current_ai_key'] = prompt_key
    reply_markup = get_ai_keyboard(prompt_key)
    await query.edit_message_text(
        f"Вы выбрали **{prompt_key.capitalize()}**.\n"
        f"Чтобы начать, изучите демо-сценарий или активируйте доступ.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['state'] = BotState.AI_SELECTION
    context.user_data['active_groq_mode'] = None
    return BotState.AI_SELECTION


async def activate_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    prompt_key = query.data.split('_')[1]
    if prompt_key == 'skilltrainer':
        from .skilltrainer import start_skilltrainer_session
        await start_skilltrainer_session(update, context)
        return BotState.AI_SELECTION
    context.user_data['active_groq_mode'] = prompt_key
    await query.edit_message_text(
        f"✅ Режим **{prompt_key.capitalize()}** активирован!\n"
        f"Напишите ваш первый запрос, и {prompt_key.capitalize()} приступит к работе.\n"
        f"Чтобы сменить режим, используйте команду /start.",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['state'] = BotState.AI_SELECTION
    return BotState.AI_SELECTION


# ==============================================================================
# ОБРАБОТЧИК ПРОГРЕССА
# ==============================================================================

async def show_progress_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    from .commands import show_usage_progress, get_personal_recommendation
    await show_usage_progress(update, context)
    user_id = query.from_user.id
    recommendation = await get_personal_recommendation(user_id)
    await query.message.reply_text(recommendation, parse_mode=ParseMode.MARKDOWN)
    return BotState.MAIN_MENU


# ==============================================================================
# НАСТРОЙКА ОБРАБОТЧИКОВ
# ==============================================================================

def setup_ai_handlers(application: Application):
    """
    Настройка AI-обработчиков (без старых menu_self/menu_business)
    """
    # Единственный обработчик главного меню — из commands.py
    from .commands import show_main_menu
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^main_menu$'))
    
    # Остальные обработчики
    application.add_handler(CallbackQueryHandler(ai_selection_handler, pattern='^ai_.*_self$|^ai_.*_business$'))
    application.add_handler(CallbackQueryHandler(show_demo_scenario, pattern='^demo_.*$'))
    application.add_handler(CallbackQueryHandler(activate_access, pattern='^activate_.*$'))
    application.add_handler(CallbackQueryHandler(show_progress_handler, pattern='^show_progress$'))
    
    logger.info("AI обработчики настроены")

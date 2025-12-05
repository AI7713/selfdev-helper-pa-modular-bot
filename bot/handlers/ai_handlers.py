"""
Обработчики AI запросов к Groq API (исправленная версия для модульной архитектуры)
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
    """
    Отправка длинных сообщений с разбивкой на части
    """
    parts = split_message_efficiently(text)
    total_parts = len(parts)
    
    for i, part in enumerate(parts, 1):
        part_prefix = prefix if total_parts == 1 else f"{prefix}*({i}/{total_parts})*\n"
        await context.bot.send_message(chat_id, f"{part_prefix}{part}", parse_mode=parse_mode)


async def handle_groq_request(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_key: str):
    """
    Обработка запроса к Groq API
    """
    # Получаем groq_client из bot_data
    groq_client: Optional[Groq] = context.application.bot_data.get('groq_client')
    
    # Проверяем доступность Groq клиента
    if not groq_client:
        await update.message.reply_text("❌ AI функции временно недоступны. Попробуйте позже.")
        return
    
    if not update.message:
        return
    
    user_id = update.message.from_user.id
    
    # Проверяем rate limiting
    if not rate_limiter.is_allowed(user_id):
        await update.message.reply_text("🚫 Слишком много запросов. Подождите минуту.")
        return
    
    # Получаем и очищаем запрос пользователя
    user_query = sanitize_user_input(update.message.text)
    
    # Получаем системный промт
    system_prompt = SYSTEM_PROMPTS.get(prompt_key, "Вы — полезный ассистент.")
    
    # Уведомляем пользователя о начале обработки
    await update.message.chat.send_message(
        f"⌛ **{prompt_key.capitalize()}** обрабатывает ваш запрос...",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Пробуем получить ответ из кэша
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
        
        # Подготавливаем сообщения для API
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_query}
        ]
        
        # Отправляем запрос к Groq API
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=4000
        )
        
        # Получаем ответ
        ai_response = chat_completion.choices[0].message.content
        
        # Кэшируем ответ
        ai_cache.cache_response(prompt_key, user_query, ai_response)
        
        # Отправляем ответ пользователю
        await send_long_message(
            update.message.chat.id,
            ai_response,
            context,
            prefix=f"🤖 Ответ {prompt_key.capitalize()}:\n",
            parse_mode=None
        )
        
        # Обновляем статистику
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
    """
    Показать демо-сценарий AI инструмента
    """
    query = update.callback_query
    await query.answer()
    
    demo_key = query.data.split('_')[1]
    text_content = DEMO_SCENARIOS.get(demo_key, "⚠️ Описание демо-сценария не найдено.")
    
    # Определяем куда возвращаться
    back_to_menu_key = 'menu_self'
    if context.user_data.get('state') == BotState.BUSINESS_MENU:
        back_to_menu_key = 'menu_business'
    
    # Создаем клавиатуру для возврата
    keyboard = [[InlineKeyboardButton("🔙 Назад к выбору AI", callback_data=back_to_menu_key)]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем описание
    await query.edit_message_text(text_content, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    
    # Обновляем состояние
    context.user_data['state'] = BotState.AI_SELECTION if back_to_menu_key == 'menu_self' else BotState.BUSINESS_MENU
    return context.user_data['state']


def get_ai_keyboard(prompt_key: str, back_button: str) -> InlineKeyboardMarkup:
    """
    Создание клавиатуры для AI инструмента
    """
    keyboard = [
        [InlineKeyboardButton("💡 Демо-сценарий (что он умеет?)", callback_data=f'demo_{prompt_key}')],
        [InlineKeyboardButton("✅ Активировать платный доступ (10 кнопок)", callback_data=f'activate_{prompt_key}')],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')],
        [InlineKeyboardButton("🔙 Назад", callback_data=back_button)]
    ]
    return InlineKeyboardMarkup(keyboard)


async def ai_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик выбора AI инструмента
    """
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    prompt_key = callback_data.split('_')[1]
    
    # Сохраняем выбранный AI инструмент
    context.user_data['current_ai_key'] = prompt_key
    
    # Определяем куда возвращаться
    if callback_data.endswith('_self'):
        back_button = 'menu_self'
    else:
        back_button = 'menu_business'
    
    # Создаем клавиатуру
    reply_markup = get_ai_keyboard(prompt_key, back_button)
    
    # Отправляем сообщение
    await query.edit_message_text(
        f"Вы выбрали **{prompt_key.capitalize()}**.\n"
        f"Чтобы начать, изучите демо-сценарий или активируйте доступ.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Обновляем состояние
    context.user_data['state'] = BotState.AI_SELECTION
    context.user_data['active_groq_mode'] = None
    
    return BotState.AI_SELECTION


async def activate_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Активация доступа к AI инструменту
    """
    query = update.callback_query
    await query.answer()
    
    prompt_key = query.data.split('_')[1]
    
    # Для skilltrainer - специальная обработка (будет в отдельном модуле)
    if prompt_key == 'skilltrainer':
        # Временно - просто сообщаем
        await query.edit_message_text(
            "🎓 **SKILLTRAINER** будет доступен в отдельном модуле.\n"
            "Сейчас переходим к основному меню.",
            parse_mode=ParseMode.MARKDOWN
        )
        # Здесь позже будет вызов start_skilltrainer_session
        return BotState.AI_SELECTION
    
    # Активируем режим для других AI инструментов
    context.user_data['active_groq_mode'] = prompt_key
    
    await query.edit_message_text(
        f"✅ Режим **{prompt_key.capitalize()}** активирован!\n"
        f"Напишите ваш первый запрос, и {prompt_key.capitalize()} приступит к работе.\n"
        f"Чтобы сменить режим, используйте команду /start.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data['state'] = BotState.AI_SELECTION
    return BotState.AI_SELECTION


async def menu_self(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик меню "Для себя"
    """
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🔮 Гримуар", callback_data='ai_grimoire_self'),
         InlineKeyboardButton("📈 Аналитик", callback_data='ai_analyzer_self')],
        [InlineKeyboardButton("🧘 Коуч", callback_data='ai_coach_self'),
         InlineKeyboardButton("💡 Генератор", callback_data='ai_generator_self')],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Вы выбрали *Для себя*. Выберите ИИ-инструмент:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data['state'] = BotState.AI_SELECTION
    context.user_data['active_groq_mode'] = None
    
    return BotState.AI_SELECTION


async def menu_business(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик меню "Для дела"
    """
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("📊 Калькулятор маркетплейсов", callback_data='menu_calculator')],
        [InlineKeyboardButton("🗣️ Переговорщик", callback_data='ai_negotiator_business'),
         InlineKeyboardButton("🎓 SKILLTRAINER", callback_data='ai_skilltrainer_business')],
        [InlineKeyboardButton("📝 Редактор", callback_data='ai_editor_business'),
         InlineKeyboardButton("🎯 Маркетолог", callback_data='ai_marketer_business')],
        [InlineKeyboardButton("🚀 HR-рекрутер", callback_data='ai_hr_business')],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Вы выбрали *Для дела*. Выберите инструмент:",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    
    context.user_data['state'] = BotState.BUSINESS_MENU
    context.user_data['active_groq_mode'] = None
    
    return BotState.BUSINESS_MENU


# ==============================================================================
# ОБРАБОТЧИК ПРОГРЕССА
# ==============================================================================

async def show_progress_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    """
    Обработчик показа прогресса
    """
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    # Используем функцию из commands.py
    from .commands import show_usage_progress, get_personal_recommendation
    
    await show_usage_progress(update, context)
    
    recommendation = await get_personal_recommendation(user_id)
    await query.message.reply_text(recommendation, parse_mode=ParseMode.MARKDOWN)
    
    return context.user_data.get('state', BotState.MAIN_MENU)


# ==============================================================================
# ФУНКЦИЯ НАСТРОЙКИ ОБРАБОТЧИКОВ
# ==============================================================================

def setup_ai_handlers(application: Application):
    """
    Настройка обработчиков AI для приложения
    """
    # Обработчики меню
    from .commands import show_main_menu
    application.add_handler(CallbackQueryHandler(show_main_menu, pattern='^main_menu$'))
    application.add_handler(CallbackQueryHandler(menu_self, pattern='^menu_self$'))
    application.add_handler(CallbackQueryHandler(menu_business, pattern='^menu_business$'))
    
    # Обработчики выбора AI инструментов
    application.add_handler(CallbackQueryHandler(ai_selection_handler, pattern='^ai_.*_self$|^ai_.*_business$'))
    
    # Обработчики демо-сценариев и активации
    application.add_handler(CallbackQueryHandler(show_demo_scenario, pattern='^demo_.*$'))
    application.add_handler(CallbackQueryHandler(activate_access, pattern='^activate_.*$'))
    
    # Обработчик прогресса
    application.add_handler(CallbackQueryHandler(show_progress_handler, pattern='^show_progress$'))
    
    logger.info("AI обработчики настроены")

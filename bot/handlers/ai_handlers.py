"""Обработчики AI-инструментов (Мудрец, Стратег, SKILLTRAINER и др.)"""
import re
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CallbackQueryHandler
from telegram.constants import ParseMode
from ..config import (
    logger, SYSTEM_PROMPTS, DEMO_SCENARIOS, BOT_VERSION
)
from ..models import (
    user_stats_cache, rate_limiter, ai_cache, BotState,
    user_conversation_history
)
from ..utils import send_long_message, split_message_efficiently, sanitize_user_input, mask_pii
from .commands import update_usage_stats
# ==============================================================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# ==============================================================================
def get_ai_keyboard(prompt_key: str) -> InlineKeyboardMarkup:
    """Создание клавиатуры для AI инструмента"""
    keyboard = [
        [InlineKeyboardButton("💡 Демо-сценарий (что он умеет?)", callback_data=f'demo_{prompt_key}')],
        [InlineKeyboardButton("✅ Активировать", callback_data=f'activate_{prompt_key}')],
        [InlineKeyboardButton("📊 Мой прогресс", callback_data='show_progress')],
        [InlineKeyboardButton("🔙 Назад в главное меню", callback_data='main_menu')]
    ]
    return InlineKeyboardMarkup(keyboard)
# ==============================================================================
# ОБРАБОТЧИК ВЫБОРА ИНСТРУМЕНТА
# ==============================================================================
async def ai_selection_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    callback_data = query.data  # Пример: "ai_growth_expert_self"
    # 🔧 УНИВЕРСАЛЬНАЯ ОБРАБОТКА: ai_<ключ>_<контекст> → <ключ>
    if callback_data.startswith("ai_"):
        # Пример: "ai_orchestrator_prof" → "orchestrator"
        prompt_key = callback_data[3:].split('_')[0]
    else:
        # Резервный вариант
        parts = callback_data.split('_', 2)
        prompt_key = parts[1] if len(parts) > 1 else "unknown"
    context.user_data['current_ai_key'] = prompt_key
    reply_markup = get_ai_keyboard(prompt_key)
    # Формируем название: "growth_expert" → "Growth Expert"
    display_name = prompt_key.replace('_', ' ').title()
    await query.edit_message_text(
        f"Вы выбрали **{display_name}**.\n"
        f"Чтобы начать, изучите демо-сценарий или активируйте доступ.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['state'] = BotState.AI_SELECTION
    context.user_data['active_groq_mode'] = None
    return BotState.AI_SELECTION
# ==============================================================================
# ДЕМО-СЦЕНАРИЙ
# ==============================================================================
async def show_demo_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    # Извлекаем ключ: demo_growth_expert → growth_expert
    demo_key = query.data.split('_', 1)[1]
    # Получаем описание из DEMO_SCENARIOS
    text_content = DEMO_SCENARIOS.get(demo_key, "⚠️ Описание демо-сценария не найдено.")
    # Кнопка "Назад в главное меню"
    keyboard = [[InlineKeyboardButton("🔙 Назад в главное меню", callback_data='main_menu')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text_content, reply_markup=reply_markup, parse_mode=None)
# ==============================================================================
# АКТИВАЦИЯ ДОСТУПА
# ==============================================================================
async def activate_access(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # 🔥 ОСНОВНОЕ ИСПРАВЛЕНИЕ: ОЧИСТКА АКТИВНОГО АГЕНТА ПРИ ЛЮБОЙ АКТИВАЦИИ
    if 'active_agent' in context.user_data:
        del context.user_data['active_agent']
    
    prompt_key = query.data.split('_', 1)[1]
    # Специальная обработка для skilltrainer
    if prompt_key == 'skilltrainer':
        from .skilltrainer import start_skilltrainer_session
        await start_skilltrainer_session(update, context)
        return BotState.SKILLTRAINER
    # 🔧 СПЕЦИАЛЬНАЯ ОБРАБОТКА ДЛЯ ОРКЕСТРАТОРА (UAF)
    if prompt_key == 'orchestrator':
        from bot.agents.implementations.orchestrator_agent import OrchestratorAgent
        user_id = update.callback_query.from_user.id
        groq_client = context.application.bot_data.get('groq_client')
        if not groq_client:
            await update.callback_query.message.reply_text("❌ AI недоступен.")
            return BotState.MAIN_MENU
        # Создаём агента и сохраняем в user_data
        agent = OrchestratorAgent(user_id, groq_client)
        context.user_data['active_agent'] = agent
        # Запускаем
        await agent.start_session(update, context)
        context.user_data['state'] = BotState.AI_SELECTION
        context.user_data['active_groq_mode'] = None  # отключаем старый режим
        return BotState.AI_SELECTION
    # Для всех остальных — обычный режим
    context.user_data['active_groq_mode'] = prompt_key
    display_name = prompt_key.replace('_', ' ').title()
    await query.edit_message_text(
        f"✅ Режим **{display_name}** активирован!\n"
        f"Напишите ваш запрос, и {display_name} приступит к работе.\n"
        f"Чтобы сменить инструмент, нажмите 🏠 Меню или введите /start.",
        parse_mode=ParseMode.MARKDOWN
    )
    context.user_data['state'] = BotState.AI_SELECTION
    return BotState.AI_SELECTION
# ==============================================================================
# ОСНОВНОЙ ОБРАБОТЧИК GROQ-ЗАПРОСОВ (С ФИЛЬТРАЦИЕЙ ПДн)
# ==============================================================================
async def handle_groq_request(update: Update, context: ContextTypes.DEFAULT_TYPE, prompt_key: str):
    groq_client = context.application.bot_data.get('groq_client')
    if not groq_client:
        await update.message.reply_text("❌ AI функции временно недоступны. Попробуйте позже.")
        return
    user_id = update.message.from_user.id
    user_query = sanitize_user_input(update.message.text)
    user_query = mask_pii(user_query)  # ← 🔒 ОБЕЗЛИЧИВАНИЕ ПДн
    # Проверка и очистка устаревшей истории (TTL = 1 час)
    if user_id in user_conversation_history:
        last_activity = user_conversation_history[user_id]['last_activity']
        if (datetime.now() - last_activity).total_seconds() > 3600:
            del user_conversation_history[user_id]
    # Формируем историю
    if user_id not in user_conversation_history:
        user_conversation_history[user_id] = {
            'history': [],
            'last_activity': datetime.now()
        }
    history = user_conversation_history[user_id]['history']
    system_prompt = SYSTEM_PROMPTS.get(prompt_key, "Ответь кратко и полезно.")
    # Подготавливаем сообщения (макс. 15 шагов)
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-14:])  # последние 14, + новый = 15
    messages.append({"role": "user", "content": user_query})
    # Отправляем "ожидание"
    await update.message.reply_text("⏳ Обрабатываю ваш запрос...", parse_mode=None)
    try:
        # Генерация ответа
        chat_completion = groq_client.chat.completions.create(
            messages=messages,
            model="llama-3.1-8b-instant",
            max_tokens=2000,
            temperature=0.7
        )
        response_text = chat_completion.choices[0].message.content
        # Сохраняем ОБЕЗЛИЧЕННЫЙ запрос и ответ
        history.append({"role": "user", "content": user_query})
        history.append({"role": "assistant", "content": response_text})
        user_conversation_history[user_id]['history'] = history[-15:]  # не более 15
        user_conversation_history[user_id]['last_activity'] = datetime.now()
        # Отправляем ответ
        await send_long_message(
            update.message.chat.id,
            response_text,
            context,
            prefix=f"🤖 {prompt_key.replace('_', ' ').title()}: ",
            parse_mode=None
        )
        await update_usage_stats(user_id, 'ai')
    except Exception as e:
        logger.error(f"Ошибка Groq: {e}")
        await update.message.reply_text("❌ Произошла ошибка при обработке запроса. Попробуйте позже.")
# ==============================================================================
# НАСТРОЙКА ОБРАБОТЧИКОВ
# ==============================================================================
def setup_ai_handlers(application: Application):
    # Основные AI-инструменты (все 11)
    ai_patterns = [
        'ai_sage_self', 'ai_strategist_self', 'ai_mentor_self', 'ai_ideator_self',
        'ai_editor_self', 'ai_growth_expert_self', 'ai_hr_advisor_self', 'ai_mediator_self',
        'ai_daily_phrase_self', 'ai_mind_horoscope_self', 'ai_daily_reflection_self'
    ]
    for pattern in ai_patterns:
        application.add_handler(CallbackQueryHandler(ai_selection_handler, pattern=f"^{pattern}$"))
    # SKILLTRAINER — отдельно, но через ту же логику выбора
    application.add_handler(CallbackQueryHandler(ai_selection_handler, pattern='^ai_skilltrainer_business$'))
    # 🔧 Добавляем обработчик для Оркестратора
    application.add_handler(CallbackQueryHandler(ai_selection_handler, pattern='^ai_orchestrator_prof$'))
    # Демо и активация
    application.add_handler(CallbackQueryHandler(show_demo_scenario, pattern=r"^demo_[a-z_]+$"))
    application.add_handler(CallbackQueryHandler(activate_access, pattern=r"^activate_[a-z_]+$"))
    logger.info("AI обработчики настроены")

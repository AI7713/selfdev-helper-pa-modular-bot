"""Полноценный обработчик SKILLTRAINER (с поддержкой кэша истории на 15 шагов + фильтрация ПДн)"""
import random
from typing import Optional
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, CallbackQueryHandler
from telegram.constants import ParseMode
from ..config import (
    logger, SKILLTRAINER_QUESTIONS, TRAINING_MODE_DESCRIPTIONS,
    SYSTEM_PROMPTS, SKILLTRAINER_GATES, SKILLTRAINER_VERSION
)
from ..models import (
    SkillSession, SessionState, TrainingMode,
    active_skill_sessions, BotState, user_conversation_history
)
from ..utils import (
    generate_hud, generate_hint, check_gate, format_finish_packet,
    split_message_efficiently, mask_pii
)
from .commands import update_usage_stats


# ==============================================================================
# ИНТЕРФЕЙС СЕССИИ
# ==============================================================================
async def start_skilltrainer_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Запуск новой сессии SKILLTRAINER"""
    query = update.callback_query
    user_id = query.from_user.id

    # Очищаем предыдущую сессию и историю
    if user_id in active_skill_sessions:
        del active_skill_sessions[user_id]
    if user_id in user_conversation_history:
        del user_conversation_history[user_id]

    session = SkillSession(user_id)
    active_skill_sessions[user_id] = session
    context.user_data['active_groq_mode'] = None
    context.user_data['state'] = BotState.SKILLTRAINER

    logger.info(f"Started SKILLTRAINER session for user {user_id}")
    await send_skilltrainer_question(update, context, session)


# ==============================================================================
# ОТПРАВКА ВОПРОСА
# ==============================================================================
async def send_skilltrainer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession):
    """Отправка текущего вопроса SKILLTRAINER с HUD"""
    hud = generate_hud(session)
    if session.current_step >= len(SKILLTRAINER_QUESTIONS):
        await finish_skilltrainer_interview(update, context, session)
        return

    question = SKILLTRAINER_QUESTIONS[session.current_step]

    if session.current_step == 6:  # Выбор режима — только через callback
        keyboard = [
            [InlineKeyboardButton("🎭 Sim", callback_data="st_mode_sim"),
             InlineKeyboardButton("💪 Drill", callback_data="st_mode_drill"),
             InlineKeyboardButton("🏗️ Build", callback_data="st_mode_build")],
            [InlineKeyboardButton("📋 Case", callback_data="st_mode_case"),
             InlineKeyboardButton("❓ Quiz", callback_data="st_mode_quiz"),
             InlineKeyboardButton("ℹ️ Описания", callback_data="st_mode_info")],
            [InlineKeyboardButton("❌ Отмена", callback_data="st_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"{hud}{question}**Выберите режим тренировки:**",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        elif update.message:
            await update.message.reply_text(
                f"{hud}{question}**Выберите режим тренировки:**",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        # Обычный вопрос — отправляем как текст
        if update.callback_query:
            await update.callback_query.edit_message_text(
                f"{hud}{question}",
                parse_mode=ParseMode.MARKDOWN
            )
        elif update.message:
            await update.message.reply_text(
                f"{hud}{question}",
                parse_mode=ParseMode.MARKDOWN
            )


# ==============================================================================
# ОБРАБОТКА ОТВЕТОВ (С ФИЛЬТРАЦИЕЙ ПДн)
# ==============================================================================
async def handle_skilltrainer_response(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession):
    """Обработка текстовых ответов пользователя в SKILLTRAINER"""
    user_text = update.message.text
    user_id = update.message.from_user.id

    if user_text.lower() in ['отмена', 'cancel', 'стоп', 'stop']:
        if user_id in active_skill_sessions:
            del active_skill_sessions[user_id]
        if user_id in user_conversation_history:
            del user_conversation_history[user_id]
        await update.message.reply_text("❌ Сессия SKILLTRAINER отменена.")
        from .calculator import show_business_menu_from_callback
        await show_business_menu_from_callback(update, context)
        return

    if user_text.lower() in ['подсказка', 'hint', 'help']:
        hint = generate_hint(session, user_text)
        session.set_hint(hint)
        await update.message.reply_text(hint)
        return

    # 🔒 ОБЕЗЛИЧИВАНИЕ ПЕРСОНАЛЬНЫХ ДАННЫХ
    sanitized_text = mask_pii(user_text)

    # Сохраняем ОБЕЗЛИЧЕННЫЙ ответ
    session.add_answer(session.current_step, sanitized_text)
    check_gate(session, "interview_complete")

    if random.random() < 0.3:
        hint = generate_hint(session)
        session.set_hint(hint)
        await update.message.reply_text(hint)

    if session.current_step < len(SKILLTRAINER_QUESTIONS):
        await send_skilltrainer_question(update, context, session)
    else:
        session.state = SessionState.MODE_SELECTION
        await send_skilltrainer_question(update, context, session)


# ==============================================================================
# ОБРАБОТКА ВЫБОРА РЕЖИМА
# ==============================================================================
async def handle_skilltrainer_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка выбора режима тренировки"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in active_skill_sessions:
        await query.edit_message_text("❌ Сессия не найдена. Начните заново через меню.")
        return

    session = active_skill_sessions[user_id]
    mode_data = query.data.replace('st_mode_', '')

    # 🔧 ИСПРАВЛЕНИЕ: обрабатываем 'info' и 'select' до проверки режимов
    if mode_data == 'info':
        descriptions_text = "**📚 ОПИСАНИЯ РЕЖИМОВ ТРЕНИРОВКИ:**\n"
        for description in TRAINING_MODE_DESCRIPTIONS.values():
            descriptions_text += f"{description}\n"
        keyboard = [[InlineKeyboardButton("🔙 Назад к выбору", callback_data="st_mode_select")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(descriptions_text, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
        return

    if mode_data == 'select':
        session.current_step = 6
        session.state = SessionState.MODE_SELECTION
        await send_skilltrainer_question(update, context, session)
        return

    if mode_data == 'cancel':
        if user_id in active_skill_sessions:
            del active_skill_sessions[user_id]
        if user_id in user_conversation_history:
            del user_conversation_history[user_id]
        await query.edit_message_text("❌ Сессия SKILLTRAINER отменена.")
        from .calculator import show_business_menu_from_callback
        await show_business_menu_from_callback(update, context)
        return

    mode_map = {
        'sim': TrainingMode.SIM,
        'drill': TrainingMode.DRILL,
        'build': TrainingMode.BUILD,
        'case': TrainingMode.CASE,
        'quiz': TrainingMode.QUIZ
    }

    if mode_data in mode_map:
        session.selected_mode = mode_map[mode_data]
        session.current_step = 7
        session.update_progress()
        check_gate(session, "mode_selected")
        await start_training_session(update, context, session)
    else:
        await query.edit_message_text("❓ Неизвестный режим.")


# ==============================================================================
# ЗАПУСК ТРЕНИРОВКИ
# ==============================================================================
async def start_training_session(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession):
    """Запуск тренировочной сессии"""
    hud = generate_hud(session)
    training_prompts = {
        TrainingMode.SIM: "🎭 **РЕЖИМ: SIM (Симуляция)**\nСейчас я создам реалистичную ситуацию для отработки вашего навыка. Готовы начать симуляцию?",
        TrainingMode.DRILL: "💪 **РЕЖИМ: DRILL (Отработка)**\nСейчас мы будем отрабатывать конкретные техники. Начнем с базовых упражнений. Готовы?",
        TrainingMode.BUILD: "🏗️ **РЕЖИМ: BUILD (Построение)**\nСейчас мы построим пошаговую стратегию развития вашего навыка. Начнем с фундамента. Готовы?",
        TrainingMode.CASE: "📋 **РЕЖИМ: CASE (Кейс)**\nСейчас мы разберем реальный кейс применения вашего навыка. Готовы к анализу?",
        TrainingMode.QUIZ: "❓ **РЕЖИМ: QUIZ (Тест)**\nСейчас я задам вопросы для проверки ваших знаний. Готовы к тесту?"
    }
    prompt = training_prompts.get(session.selected_mode, "Начинаем тренировку...")
    keyboard = [
        [InlineKeyboardButton("✅ Начать тренировку", callback_data="st_start_training")],
        [InlineKeyboardButton("🔙 Выбрать другой режим", callback_data="st_mode_select")],
        [InlineKeyboardButton("❌ Завершить", callback_data="st_finish_early")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        await update.callback_query.edit_message_text(
            f"{hud}{prompt}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    elif update.message:
        await update.message.reply_text(
            f"{hud}{prompt}",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )


# ==============================================================================
# ГЕНЕРАЦИЯ ЗАДАНИЯ
# ==============================================================================
async def handle_training_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Генерация и отправка тренировочного задания через Groq"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in active_skill_sessions:
        await query.edit_message_text("❌ Сессия не найдена.")
        return

    session = active_skill_sessions[user_id]
    session.state = SessionState.TRAINING
    groq_client = context.application.bot_data.get('groq_client')

    if groq_client:
        try:
            answers_text = "".join([f"Вопрос {i+1}: {answer}" for i, answer in session.answers.items()])
            training_request = f"""Пользователь хочет развить навык. Вот его ответы на диагностику:
{answers_text}
Выбранный режим тренировки: {session.selected_mode.name if session.selected_mode else 'Не выбран'}
Создай одно тренировочное задание в выбранном режиме. Задание должно быть:
1. Практическим и конкретным
2. Соответствовать выбранному режиму
3. Иметь четкую инструкцию
4. Быть выполнимым за 5-15 минут
5. Включать критерии успешного выполнения (DOD)
Формат ответа:
**ЗАДАНИЕ:** [Название задания]
**ИНСТРУКЦИЯ:** [Пошаговая инструкция]
**КРИТЕРИИ УСПЕХА (DOD):
1. [Критерий 1]
2. [Критерий 2]
3. [Критерий 3]
**ПОДСКАЗКА:** [Короткая подсказка ≤240 символов]"""

            messages = [{"role": "system", "content": SYSTEM_PROMPTS['skilltrainer']}, {"role": "user", "content": training_request}]
            await query.edit_message_text(f"{generate_hud(session)}🎯 Генерирую задание...")
            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.1-8b-instant",
                max_tokens=1500
            )
            training_task = chat_completion.choices[0].message.content
            session.data = {'training_task': training_task}
            session.training_complete = True
            check_gate(session, "training_complete")
            keyboard = [
                [InlineKeyboardButton("✅ Задание выполнено", callback_data="st_task_done")],
                [InlineKeyboardButton("💡 Нужна подсказка", callback_data="st_need_hint")],
                [InlineKeyboardButton("🔄 Другое задание", callback_data="st_another_task")],
                [InlineKeyboardButton("🏁 Завершить сессию", callback_data="st_finish_session")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"{generate_hud(session)}{training_task}",
                reply_markup=reply_markup,
                parse_mode=ParseMode.MARKDOWN
            )
        except Exception as e:
            logger.error(f"Ошибка генерации задания SKILLTRAINER: {e}")
            await query.edit_message_text(
                f"{generate_hud(session)}❌ Ошибка при генерации задания. Попробуйте еще раз или выберите другой режим.",
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await query.edit_message_text(
            f"{generate_hud(session)}❌ Groq API не доступен. SKILLTRAINER не может работать без AI.",
            parse_mode=ParseMode.MARKDOWN
        )


# ==============================================================================
# ЗАВЕРШЕНИЕ ИНТЕРВЬЮ
# ==============================================================================
async def finish_skilltrainer_interview(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession):
    """Завершение интервью и переход к выбору режима"""
    session.state = SessionState.MODE_SELECTION
    await send_skilltrainer_question(update, context, session)


# ==============================================================================
# ЗАВЕРШЕНИЕ СЕССИИ
# ==============================================================================
async def finish_skilltrainer_session(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession = None):
    """Формирование и отправка Finish Packet"""
    if not session:
        user_id = update.callback_query.from_user.id if update.callback_query else update.message.from_user.id
        session = active_skill_sessions.get(user_id)
        if not session:
            if update.callback_query:
                await update.callback_query.edit_message_text("❌ Сессия не найдена.")
            return

    session.state = SessionState.FINISH
    session.progress = 1.0
    groq_client = context.application.bot_data.get('groq_client')

    if groq_client:
        try:
            answers_text = "".join([f"Шаг {i+1}: {answer}" for i, answer in session.answers.items()])
            finish_request = f"""На основе диагностики пользователя сформируй Finish Packet (Итоговый пакет).
ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
{answers_text}
Выбранный режим тренировки: {session.selected_mode.name if session.selected_mode else 'Не выбран'}
СФОРМИРУЙ FINISH PACKET СО СЛЕДУЮЩИМИ РАЗДЕЛАМИ:
1. **КРАТКАЯ ДИАГНОСТИКА** - основные выводы из ответов
2. **РЕКОМЕНДОВАННЫЕ МЕТОДИКИ** - 3-5 конкретных методик для развития навыка
3. **ПЛАН ТРЕНИРОВОК** - понедельный план на 4 недели
4. **ИНСТРУМЕНТЫ И РЕСУРСЫ** - полезные инструменты, книги, курсы
5. **КРИТЕРИИ ПРОГРЕССА** - как отслеживать улучшения
6. **ЧЕК-ЛИСТ ПРОВЕРКИ** - что проверить через 2 недели
Будь конкретным, практичным и мотивирующим."""

            messages = [{"role": "system", "content": SYSTEM_PROMPTS['skilltrainer']}, {"role": "user", "content": finish_request}]
            if update.callback_query:
                await update.callback_query.edit_message_text(f"{generate_hud(session)}🎓 Формирую Finish Packet...")
            elif update.message:
                await update.message.reply_text(f"{generate_hud(session)}🎓 Формирую Finish Packet...")

            chat_completion = groq_client.chat.completions.create(
                messages=messages,
                model="llama-3.1-8b-instant",
                max_tokens=4000
            )
            ai_response = chat_completion.choices[0].message.content
            session.finish_packet = format_finish_packet(session, ai_response)
            await update_usage_stats(session.user_id, 'skilltrainer')

            # Очистка после завершения
            if session.user_id in active_skill_sessions:
                del active_skill_sessions[session.user_id]
            if session.user_id in user_conversation_history:
                del user_conversation_history[session.user_id]

            # Финальное меню
            keyboard = [
                [InlineKeyboardButton("🎁 Пригласить друга", callback_data="st_referral")],
                [InlineKeyboardButton("🔄 Новая сессия", callback_data="st_new_session")],
                [InlineKeyboardButton("🔙 В меню", callback_data="main_menu")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            parts = split_message_efficiently(session.finish_packet)
            for part in parts:
                if update.callback_query:
                    await update.callback_query.message.reply_text(part)
                elif update.message:
                    await update.message.reply_text(part)

            if update.callback_query:
                await update.callback_query.message.reply_text(
                    "✅ **СЕССИЯ SKILLTRAINER ЗАВЕРШЕНА!**\nВы можете пригласить друга или начать новую сессию.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
            elif update.message:
                await update.message.reply_text(
                    "✅ **СЕССИЯ SKILLTRAINER ЗАВЕРШЕНА!**\nВы можете пригласить друга или начать новую сессию.",
                    reply_markup=reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.error(f"Ошибка генерации Finish Packet: {e}")
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    "❌ Ошибка при формировании Finish Packet. Основные результаты сохранены.\n"
                    f"Ваши ответы: {len(session.answers)} из 7\n"
                    f"Режим: {session.selected_mode.name if session.selected_mode else 'Не выбран'}",
                    parse_mode=ParseMode.MARKDOWN
                )
    else:
        if update.callback_query:
            await update.callback_query.edit_message_text(
                "❌ Groq API не доступен. Не могу сформировать Finish Packet.\nВаши ответы сохранены. Попробуйте позже.",
                parse_mode=ParseMode.MARKDOWN
            )


# ==============================================================================
# ОБРАБОТКА ДЕЙСТВИЙ ПОСЛЕ ЗАДАНИЯ
# ==============================================================================
async def handle_skilltrainer_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка действий пользователя после получения задания"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    action = query.data

    if action == "st_referral":
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        await query.message.reply_text(
            f"🎁 **Пригласите друга — получите бонусы!**\nВаша ссылка:\n`{ref_link}`\nПросто отправьте её другу в Telegram!",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    if action == "st_new_session":
        await start_skilltrainer_session(update, context)
        return

    if user_id not in active_skill_sessions:
        await query.edit_message_text("❌ Сессия не найдена.")
        return

    session = active_skill_sessions[user_id]

    if action == "st_task_done":
        await query.edit_message_text(
            f"{generate_hud(session)}\n✅ **Отлично! Задание выполнено.**\nХотите получить еще одно задание или завершить сессию?",
            parse_mode=ParseMode.MARKDOWN
        )
        keyboard = [
            [InlineKeyboardButton("🔄 Еще задание", callback_data="st_another_task")],
            [InlineKeyboardButton("🏁 Завершить сессию", callback_data="st_finish_session")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("Выберите действие:", reply_markup=reply_markup)

    elif action == "st_need_hint":
        hint = generate_hint(session)
        session.set_hint(hint)
        await query.message.reply_text(hint)

    elif action == "st_another_task":
        await start_training_session(update, context, session)

    elif action in ("st_finish_early", "st_finish_session"):
        await finish_skilltrainer_session(update, context, session)


# ==============================================================================
# НАСТРОЙКА ОБРАБОТЧИКОВ
# ==============================================================================
def setup_skilltrainer_handlers(application: Application):
    """Регистрация всех обработчиков SKILLTRAINER"""
    application.add_handler(CallbackQueryHandler(handle_skilltrainer_mode, pattern='^st_mode_.+$'))
    application.add_handler(CallbackQueryHandler(handle_training_start, pattern='^st_start_training$'))
    application.add_handler(CallbackQueryHandler(handle_skilltrainer_actions, pattern='^st_.+$'))
    logger.info("SKILLTRAINER обработчики настроены")

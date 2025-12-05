"""
Обработчик калькулятора маркетплейса
"""
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, Application, MessageHandler, filters, CallbackQueryHandler
from telegram.constants import ParseMode

from ..config import (
    logger, CALCULATOR_STEPS, BENCHMARKS
)
from ..models import BotState
from ..utils import get_calculator_data_safe
from .commands import update_usage_stats


# ==============================================================================
# ФУНКЦИИ КАЛЬКУЛЯТОРА
# ==============================================================================

def calculate_economy_metrics(data):
    себестоимость = data[0]
    цена = data[1]
    комиссия_процент = data[2]
    логистика_процент = data[3]
    acos_процент = data[4]
    налог_процент = data[5]
    
    выручка = цена
    комиссия = выручка * комиссия_процент / 100
    логистика = выручка * логистика_процент / 100
    cm1 = выручка - себестоимость - комиссия - логистика
    реклама = выручка * acos_процент / 100
    cm2 = cm1 - реклама
    налог = выручка * налог_процент / 100
    чистая_прибыль = cm2 - налог
    
    наценка_процент = ((цена - себестоимость) / себестоимость) * 100 if себестоимость > 0 else 0
    маржа_cm1_процент = (cm1 / выручка) * 100 if выручка > 0 else 0
    маржа_cm2_процент = (cm2 / выручка) * 100 if выручка > 0 else 0
    чистая_маржа_процент = (чистая_прибыль / выручка) * 100 if выручка > 0 else 0
    
    return {
        'выручка': выручка,
        'себестоимость': себестоимость,
        'комиссия': комиссия,
        'комиссия_%': комиссия_процент,
        'логистика': логистика,
        'логистика_%': логистика_процент,
        'cm1': cm1,
        'маржа_cm1_%': маржа_cm1_процент,
        'реклама': реклама,
        'acos_%': acos_процент,
        'cm2': cm2,
        'маржа_cm2_%': маржа_cm2_процент,
        'налог': налог,
        'налог_%': налог_процент,
        'чистая_прибыль': чистая_прибыль,
        'чистая_маржа_%': чистая_маржа_процент,
        'наценка_%': наценка_процент
    }


def generate_recommendations(metrics):
    recommendations = []
    
    if metrics['наценка_%'] > BENCHMARKS['наценка']['высокая']:
        recommendations.append("🚀 Отличная наценка! Товар имеет высокий потенциал прибыли")
    elif metrics['наценка_%'] < BENCHMARKS['наценка']['низкая']:
        recommendations.append("📈 Низкая наценка. Рассмотрите повышение цены или поиск поставщика с лучшими условиями")
    
    if metrics['комиссия_%'] > BENCHMARKS['комиссия_mp']['высокая']:
        recommendations.append("📊 Комиссия выше среднего. Рассмотрите маркетплейсы с меньшей комиссией")
    elif metrics['комиссия_%'] < BENCHMARKS['комиссия_mp']['низкая']:
        recommendations.append("💰 Низкая комиссия - хорошие условия!")
    
    if metrics['логистика_%'] > BENCHMARKS['логистика']['высокая']:
        recommendations.append("🚚 Логистика дороговата. Ищите способы оптимизации доставки или упаковки")
    elif metrics['логистика_%'] < BENCHMARKS['логистика']['низкая']:
        recommendations.append("📦 Логистика эффективна!")
    
    if metrics['acos_%'] > BENCHMARKS['acos']['высокий']:
        recommendations.append("📢 Высокий ACOS. Оптимизируйте рекламные кампании или когорты")
    elif metrics['acos_%'] < BENCHMARKS['acos']['низкий']:
        recommendations.append("🎯 Эффективная реклама!")
    
    if metrics['чистая_маржа_%'] > BENCHMARKS['чистая_маржа']['высокая']:
        recommendations.append("✅ Отличная рентабельность! Товар готов к масштабированию")
    elif metrics['чистая_маржа_%'] < BENCHMARKS['чистая_маржа']['низкая']:
        recommendations.append("💸 Низкая рентабельность. Рассмотрите повышение цены или снижение закупочной стоимости")
    
    return recommendations if recommendations else ["📊 Показатели в норме. Продолжайте в том же духе!"]


async def calculate_and_show_results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = [get_calculator_data_safe(context, i) for i in range(6)]
    metrics = calculate_economy_metrics(data)
    recommendations = generate_recommendations(metrics)
    
    report = f"""📊 **ФИНАНСОВЫЙ АНАЛИЗ ТОВАРА**
💰 **ВЫРУЧКА И ЗАТРАТЫ:**
• Выручка: {metrics['выручка']:.1f} ₽
• Себестоимость: {metrics['себестоимость']:.1f} ₽
• Комиссия MP: {metrics['комиссия']:.1f} ₽ ({metrics['комиссия_%']:.1f}%)
• Логистика FBS: {metrics['логистика']:.1f} ₽ ({metrics['логистика_%']:.1f}%)
• Реклама (ACOS): {metrics['реклама']:.1f} ₽ ({metrics['acos_%']:.1f}%)
• Налог УСН: {metrics['налог']:.1f} ₽ ({metrics['налог_%']:.1f}%)
🎯 **УРОВНИ ПРИБЫЛИ:**
• CM1 (до рекламы): {metrics['cm1']:.1f} ₽ ({metrics['маржа_cm1_%']:.1f}%)
• CM2 (после рекламы): {metrics['cm2']:.1f} ₽ ({metrics['маржа_cm2_%']:.1f}%)
• Чистая прибыль: {metrics['чистая_прибыль']:.1f} ₽ ({metrics['чистая_маржа_%']:.1f}%)
📈 **КЛЮЧЕВЫЕ МЕТРИКИ:**
• Наценка: {metrics['наценка_%']:.1f}% {'🚀' if metrics['наценка_%'] > 300 else '✅' if metrics['наценка_%'] > 200 else '📊'}
• Рентабельность: {metrics['чистая_маржа_%']:.1f}% {'✅' if metrics['чистая_маржа_%'] > 30 else '📊'}
💡 **РЕКОМЕНДАЦИИ:**
"""
    
    for rec in recommendations:
        report += f"• {rec}\n"
    
    keyboard = [
        [KeyboardButton("🔄 Новый расчет")],
        [KeyboardButton("🔙 Назад")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(report, reply_markup=reply_markup, parse_mode=ParseMode.MARKDOWN)
    await update_usage_stats(update.message.from_user.id, 'calculator')


async def start_economy_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data['calculator_step'] = 0
    context.user_data['calculator_data'] = {}
    context.user_data['state'] = BotState.CALCULATOR
    
    if update.callback_query:
        await update.callback_query.message.reply_text(
            "🛍️ **РАСЧЕТ ЭКОНОМИКИ МАРКЕТПЛЕЙСА**\n"
            "Введите данные вашего товара:\n"
            + CALCULATOR_STEPS[0],
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🛍️ **РАСЧЕТ ЭКОНОМИКИ МАРКЕТПЛЕЙСА**\n"
            "Введите данные вашего товара:\n"
            + CALCULATOR_STEPS[0],
            parse_mode=ParseMode.MARKDOWN
        )


async def handle_economy_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.message.text
    step = context.user_data.get('calculator_step', 0)
    
    if text == "🔙 Назад":
        if step == 0:
            # Возвращаемся в главное меню через /start
            from .commands import start
            await start(update, context)
        else:
            context.user_data['calculator_step'] = step - 1
            await update.message.reply_text(CALCULATOR_STEPS[step - 1])
        return
    
    if text == "🔄 Новый расчет":
        context.user_data['calculator_step'] = 0
        context.user_data['calculator_data'] = {}
        await start_economy_calculator(update, context)
        return
    
    try:
        value = float(text)
        if value < 0:
            await update.message.reply_text("❌ Число должно быть положительным. Попробуйте еще раз:")
            return
        
        context.user_data['calculator_data'][step] = value
        context.user_data['calculator_step'] = step + 1
        
        if step + 1 < len(CALCULATOR_STEPS):
            await update.message.reply_text(CALCULATOR_STEPS[step + 1])
        else:
            await calculate_and_show_results(update, context)
    
    except ValueError:
        await update.message.reply_text("❌ Пожалуйста, введите число:")


# ==============================================================================
# ОБРАБОТЧИК CALLBACK ДЛЯ МЕНЮ
# ==============================================================================

async def menu_calculator(update: Update, context: ContextTypes.DEFAULT_TYPE) -> BotState:
    query = update.callback_query
    await query.answer()
    
    context.user_data['state'] = BotState.CALCULATOR
    context.user_data['active_groq_mode'] = None
    
    await start_economy_calculator(update, context)
    return BotState.CALCULATOR


# ==============================================================================
# НАВИГАЦИОННАЯ ФУНКЦИЯ
# ==============================================================================

async def show_business_menu_from_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Калькулятор маркетплейсов", callback_data='menu_calculator')],
        [InlineKeyboardButton("🗣️ Переговорщик", callback_data='ai_negotiator_business'),
         InlineKeyboardButton("🎓 SKILLTRAINER", callback_data='ai_skilltrainer_business')],
        [InlineKeyboardButton("📝 Редактор", callback_data='ai_editor_business'),
         InlineKeyboardButton("🎯 Маркетолог", callback_data='ai_marketer_business')],
        [InlineKeyboardButton("🚀 HR-рекрутер", callback_data='ai_hr_business')],
        [InlineKeyboardButton("🔙 В главное меню", callback_data='main_menu')]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "🚀 **ДЛЯ ДЕЛА**\nИнструменты для профессионального роста и бизнеса:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text(
            "🚀 **ДЛЯ ДЕЛА**\nИнструменты для профессионального роста и бизнеса:",
            reply_markup=reply_markup,
            parse_mode=ParseMode.MARKDOWN
        )


# ==============================================================================
# ФУНКЦИЯ НАСТРОЙКИ ОБРАБОТЧИКОВ
# ==============================================================================

def setup_calculator_handlers(application: Application):
    application.add_handler(CallbackQueryHandler(menu_calculator, pattern='^menu_calculator$'))
    logger.info("Обработчики калькулятора настроены")

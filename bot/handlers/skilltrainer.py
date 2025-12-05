"""
Заглушка для модуля SKILLTRAINER (будет реализован позже)
"""
from telegram import Update
from telegram.ext import ContextTypes, Application

from ..config import logger
from ..models import SkillSession


async def handle_skilltrainer_response(update: Update, context: ContextTypes.DEFAULT_TYPE, session: SkillSession):
    """Временная заглушка"""
    await update.message.reply_text("🎓 SKILLTRAINER будет реализован в следующей версии")


async def start_skilltrainer_session(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Временная заглушка"""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🎓 SKILLTRAINER будет доступен в следующем обновлении")


def setup_skilltrainer_handlers(application: Application):
    """Настройка заглушки"""
    logger.info("SKILLTRAINER заглушка настроена")

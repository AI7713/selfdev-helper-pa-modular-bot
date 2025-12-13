# bot/agents/implementations/orchestrator_agent.py
import os
from typing import Dict, Any, Optional
from telegram import Update
from telegram.ext import ContextTypes
from ..core.agent_base import BaseAgent
from ..core.state_machine import StateMachine
from ..core.gate_manager import GateManager
from ..core.ui_manager import generate_hud
from ..core.command_processor import CommandProcessor
from ..core.llm_client import LLMClient

class OrchestratorAgent(BaseAgent):
    """
    Агент «Оркестратор проекта с коллегией экспертов» — V2.5
    """

    def __init__(self, user_id: int, groq_client):
        super().__init__(user_id, "Оркестратор")
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'orchestrator.yaml')
        prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'orchestrator.txt')
        self.state_machine = StateMachine(config_path)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()
        self.gate_manager = GateManager(self.state_machine.config.get('gates', {}))
        self.command_processor = CommandProcessor()
        self.llm_client = LLMClient(groq_client)
        self._register_commands()
        self.session_data['settings'] = self.state_machine.config.get('default_settings', {})
    
    def _register_commands(self):
        commands = self.state_machine.config.get('commands', [])
        for cmd in commands:
            name = cmd['name']
            aliases = cmd.get('alias', [])
            for alias in aliases:
                self.command_processor.register(alias.lstrip('/'), self._handle_command)
    
    async def start_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.session_data['current_block'] = 'B0'
        message = (
            "👋 Я — Оркестратор.\n"
            "Помогу вам превратить идею в измеримый результат с участием коллегии экспертов.\n\n"
            "Опишите:\n• Желаемый результат\n• Дедлайн\n• Для кого (целевая аудитория)"
        )
        if update.callback_query:
            await update.callback_query.message.reply_text(message)
            await update.callback_query.answer()
        elif update.message:
            await update.message.reply_text(message)
        else:
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id=chat_id, text=message)

    async def handle_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        # 1. Сохраняем ввод пользователя
        current_block = self.session_data['current_block']
        if current_block == 'B0':
            self.session_data['raw_description'] = user_input
        elif current_block == 'B1.a':
            self.session_data['refinements'] = user_input

        # 2. Проверка команд
        cmd_info = self.command_processor.process(user_input, self.session_data)
        if cmd_info:
            handler = cmd_info['handler']
            if handler:
                await handler(update, context, cmd_info)
            return

        # 3. Гейт — только если явно требуется
        if self.state_machine.is_gated(current_block):
            passed, msg = self.gate_manager.check_gate(current_block, self.session_data)
            if not passed:
                await update.message.reply_text(f"⛔ {msg}\nИсправьте и повторите.")
                return

        # 4. Вызов LLM
        system_prompt = self._build_dynamic_prompt(current_block)
        response = await self.llm_client.call_llm(system_prompt, user_input)
        if not response:
            await update.message.reply_text("❌ Не удалось получить ответ. Попробуйте позже.")
            return

        # 🔥 ВАЖНО: НЕ ИЗМЕНЯЕМ БЛОК АВТОМАТИЧЕСКИ
        # next_block = self._determine_next_block(current_block, response)
        # self.session_data['current_block'] = next_block

        # 5. Отправка ответа
        hud = generate_hud(self.agent_name, self.session_data)
        full_response = f"{hud}\n\n{response}"
        from bot.utils import send_long_message
        await send_long_message(
            chat_id=update.message.chat.id,
            text=full_response,
            context=context,
            prefix="",
            parse_mode=None
        )

        # 6. КНОПКИ — ТОЛЬКО ПОСЛЕ B1.b (временно)
        if current_block == 'B0':
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            keyboard = [[InlineKeyboardButton("➡️ Продолжить к уточнениям", callback_data="orch_action:go_to_B1a")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("Нажмите, чтобы продолжить:", reply_markup=reply_markup)

    def _build_dynamic_prompt(self, block_id: str) -> str:
        block_config = self.state_machine.get_block_config(block_id)
        block_title = block_config.get('title', block_id)
        block_desc = block_config.get('description', '')
        prompt = self.system_prompt + "\n\n"
        prompt += f"[ТЕКУЩИЙ БЛОК: {block_id} — {block_title}]\n"
        if block_desc:
            prompt += f"[ИНСТРУКЦИЯ: {block_desc}]\n"
        settings = self.session_data['settings']
        prompt += f"[НАСТРОЙКИ: mode={settings.get('mode', 'coach')}, risk_appetite={settings.get('risk_appetite', 'medium')}]\n"
        return prompt

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd_info: Dict[str, Any]):
        command = cmd_info['command']
        args = cmd_info.get('args', '')
        if command == 's-check':
            await update.message.reply_text("🔍 Запускаю S-CHECK...")
        elif command == 'вернуться':
            if args:
                self.session_data['current_block'] = args.strip()
                await update.message.reply_text(f"↩️ Возврат к блоку: {args}")
            else:
                await update.message.reply_text("Укажите ID блока, например: `/вернуться B1.b`")
        else:
            await update.message.reply_text(f"🛠️ Команда `{command}` получена.")

    async def finish_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.session_data['active'] = False
        await update.message.reply_text("✅ Сессия «Оркестратора» завершена.")

# bot/agents/implementations/orchestrator_agent.py
import os
from typing import Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
        current_block = self.session_data['current_block']

        # 1. Сохраняем ввод пользователя по блокам
        if current_block == 'B0':
            self.session_data['raw_description'] = user_input
        elif current_block == 'B1.a':
            self.session_data['refinements'] = user_input

        # 2. Обработка команд (например, /s-check, /вернуться)
        cmd_info = self.command_processor.process(user_input, self.session_data)
        if cmd_info:
            handler = cmd_info['handler']
            if handler:
                await handler(update, context, cmd_info)
            return

        # 3. Вызов LLM с динамическим промтом
        system_prompt = self._build_dynamic_prompt(current_block)
        response = await self.llm_client.call_llm(system_prompt, user_input)
        if not response:
            await update.message.reply_text("❌ Не удалось получить ответ. Попробуйте позже.")
            return

        # 4. Отправка ответа с HUD
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

        # 5. КНОПКИ — в зависимости от блока
        await self._send_contextual_buttons(update, context, current_block)

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

    async def _send_contextual_buttons(self, update: Update, context: ContextTypes.DEFAULT_TYPE, block_id: str):
        """Отправка кнопок в зависимости от текущего блока"""
        if block_id == 'B0':
            keyboard = [[InlineKeyboardButton("➡️ Перейти к уточнениям (B1.a)", callback_data="orch_action:go_to_B1a")]]
            await update.message.reply_text(
                "Что дальше?",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        elif block_id == 'B1.b':
            keyboard = [
                [InlineKeyboardButton("✅ Подтвердить формулировку", callback_data="orch_action:confirm_B1b")],
                [InlineKeyboardButton("🔁 Уточнить ЦА", callback_data="orch_action:refine_ca")],
                [InlineKeyboardButton("📊 Показать Mini Pre-flight", callback_data="orch_action:show_preflight")],
                [InlineKeyboardButton("🔍 /s-check", callback_data="orch_cmd:s-check")]
            ]
            await update.message.reply_text(
                "Выберите действие:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        # Дополнительные блоки — по мере реализации

    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd_info: Dict[str, Any]):
        command = cmd_info['command']
        args = cmd_info.get('args', '')
        if command == 's-check':
            await update.message.reply_text("🔍 Запускаю S-CHECK (Self-Critique)...")
        elif command == 'вернуться':
            target_block = args.strip() if args else 'B0'
            self.session_data['current_block'] = target_block
            await update.message.reply_text(f"↩️ Возврат к блоку: {target_block}")
        elif command == 'benchmarks':
            await update.message.reply_text("📈 Запрашиваю бенчмарки...")
        else:
            await update.message.reply_text(f"🛠️ Команда `{command}` получена.")

    async def finish_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        self.session_data['active'] = False
        await update.message.reply_text("✅ Сессия «Оркестратора» завершена.")

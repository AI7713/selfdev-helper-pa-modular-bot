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
        
        # Пути к конфигурации
        config_path = os.path.join(os.path.dirname(__file__), '..', 'configs', 'orchestrator.yaml')
        prompt_path = os.path.join(os.path.dirname(__file__), '..', 'prompts', 'orchestrator.txt')
        
        # Загрузка конфигурации и промта
        self.state_machine = StateMachine(config_path)
        with open(prompt_path, 'r', encoding='utf-8') as f:
            self.system_prompt = f.read()
        
        # Инициализация компонентов ядра
        self.gate_manager = GateManager(self.state_machine.config.get('gates', {}))
        self.command_processor = CommandProcessor()
        self.llm_client = LLMClient(groq_client)
        
        # Регистрация команд
        self._register_commands()
        
        # Инициализация настроек из YAML
        self.session_data['settings'] = self.state_machine.config.get('default_settings', {})
    
    def _register_commands(self):
        """Регистрация всех команд из конфига"""
        commands = self.state_machine.config.get('commands', [])
        for cmd in commands:
            name = cmd['name']
            aliases = cmd.get('alias', [])
            # Для простоты — все команды ведут к одному обработчику
            for alias in aliases:
                self.command_processor.register(alias.lstrip('/'), self._handle_command)
    
    async def start_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Запуск сессии: B0 — Презентация"""
        self.session_data['current_block'] = 'B0'
        message = (
            "👋 Я — Оркестратор.\n"
            "Помогу вам превратить идею в измеримый результат с участием коллегии экспертов.\n\n"
            "Опишите:\n• Желаемый результат\n• Дедлайн\n• Для кого (целевая аудитория)"
        )
        # 🔧 Безопасная отправка — через callback_query ИЛИ message
        if update.callback_query:
            await update.callback_query.message.reply_text(message)
            await update.callback_query.answer()  # подтверждаем нажатие
        elif update.message:
            await update.message.reply_text(message)
        else:
            # Резервный вариант — отправка по chat_id
            chat_id = update.effective_chat.id
            await context.bot.send_message(chat_id=chat_id, text=message)
    
    async def handle_input(self, update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
        """Обработка входного сообщения"""
        # 1. Проверка команд
        cmd_info = self.command_processor.process(user_input, self.session_data)
        if cmd_info:
            handler = cmd_info['handler']
            if handler:
                await handler(update, context, cmd_info)
            return
        
        # 2. Получение текущего блока
        current_block = self.session_data['current_block']
        
        # 3. Если блок требует гейта — проверяем
        if self.state_machine.is_gated(current_block):
            passed, msg = self.gate_manager.check_gate(current_block, self.session_data)
            if not passed:
                await update.message.reply_text(f"⛔ {msg}\n\nИсправьте и повторите.")
                return
        
        # 4. Генерация ответа через LLM
        system_prompt = self._build_dynamic_prompt(current_block)
        response = await self.llm_client.call_llm(system_prompt, user_input)
        
        if not response:
            await update.message.reply_text("❌ Не удалось получить ответ. Попробуйте позже.")
            return
        
        # 5. Обновление состояния (в простом режиме — первый доступный следующий блок)
        next_block = self._determine_next_block(current_block, response)
        self.session_data['current_block'] = next_block
        
        # 6. Отправка ответа + HUD
        hud = generate_hud(self.agent_name, self.session_data)
        full_response = f"{hud}\n\n{response}"
        await update.message.reply_text(full_response)
    
    def _build_dynamic_prompt(self, block_id: str) -> str:
        """Сборка системного промта с учётом текущего блока и настроек"""
        block_config = self.state_machine.get_block_config(block_id)
        block_title = block_config.get('title', block_id)
        block_desc = block_config.get('description', '')
        
        prompt = self.system_prompt + "\n\n"
        prompt += f"[ТЕКУЩИЙ БЛОК: {block_id} — {block_title}]\n"
        if block_desc:
            prompt += f"[ИНСТРУКЦИЯ: {block_desc}]\n"
        
        # Добавление настроек
        settings = self.session_data['settings']
        prompt += f"[НАСТРОЙКИ: mode={settings.get('mode', 'coach')}, risk_appetite={settings.get('risk_appetite', 'medium')}]\n"
        
        return prompt
    
    def _determine_next_block(self, current_block: str, response: str) -> str:
        """Определение следующего блока (в простом варианте — первый из переходов)"""
        next_blocks = self.state_machine.get_next_blocks(current_block)
        return next_blocks[0] if next_blocks else current_block
    
    async def _handle_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE, cmd_info: Dict[str, Any]):
        """Обработка внутренних команд (упрощённо)"""
        command = cmd_info['command']
        args = cmd_info.get('args', '')
        
        if command == 's-check':
            await update.message.reply_text("🔍 Запускаю S-CHECK (Self-Critique)...")
            # Здесь будет вызов LLM с шаблоном S-CHECK
        elif command == 'вернуться':
            if args:
                self.session_data['current_block'] = args.strip()
                await update.message.reply_text(f"↩️ Возврат к блоку: {args}")
            else:
                await update.message.reply_text("Укажите ID блока, например: `/вернуться B1.b`")
        else:
            await update.message.reply_text(f"🛠️ Команда `{command}` получена. Реализация — в разработке.")
    
    async def finish_session(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Завершение сессии"""
        self.session_data['active'] = False
        await update.message.reply_text("✅ Сессия «Оркестратора» завершена.")

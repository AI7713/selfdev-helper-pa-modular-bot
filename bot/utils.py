"""Вспомогательные функции бота"""
import random
import re
from typing import List, Tuple
from datetime import datetime
from .models import SkillSession
from .config import SKILLTRAINER_QUESTIONS, SKILLTRAINER_GATES, SKILLTRAINER_VERSION


def sanitize_user_input(text: str, max_length: int = 2000) -> str:
    """Очистка пользовательского ввода от опасных символов"""
    if not text:
        return ""
    cleaned = re.sub(r'[<>{}`|\\\-\t]', '', text)
    cleaned = ''.join(char for char in cleaned if char.isprintable() or char in '\r')
    return cleaned[:max_length]


def mask_pii(text: str) -> str:
    """Заменяет персональные данные на токены (PII masking для 152-ФЗ)"""
    # 1. ФИО (3 слова с заглавной буквы)
    text = re.sub(r'\b([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)\s+([А-ЯЁ][а-яё]+)\b', '<PERSON>', text)
    # 2. Имя после "зовут", "имя" и т.д. (любой регистр, одно или несколько слов)
    text = re.sub(r'\b(зовут|имя|это|зовут\s+меня|зовут\s+его|зовут\s+её)\s+([а-яёa-z\s]{2,30})', r'\1 <PERSON>', text, flags=re.IGNORECASE)
    # 3. Email
    text = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '<EMAIL>', text)
    # 4. Телефон
    text = re.sub(r'\+?\d[\d\-\s\(\)]{7,}\d', '<PHONE>', text)
    # 5. ИНН (10 или 12 цифр)
    text = re.sub(r'\b\d{10}\b|\b\d{12}\b', '<TAX_ID>', text)
    # 6. Банковская карта
    text = re.sub(r'\b(?:\d{4}[\s\-]?){3}\d{4}\b', '<CARD>', text)
    # 7. Паспорт
    text = re.sub(r'\b\d{2}\s\d{2}\s\d{6}\b', '<PASSPORT>', text)
    return text


def split_message_efficiently(text: str, max_length: int = 4096) -> List[str]:
    """Разделение длинного сообщения на части для Telegram"""
    if len(text) <= max_length:
        return [text]
    sentences = text.split('. ')
    parts = []
    current_part = ""
    for sentence in sentences:
        test_part = current_part + sentence + ". "
        if len(test_part) <= max_length:
            current_part = test_part
        else:
            if current_part:
                parts.append(current_part.strip())
            current_part = sentence + ". "
    if current_part:
        parts.append(current_part.strip())
    final_parts = []
    for part in parts:
        if len(part) > max_length:
            for i in range(0, len(part), max_length):
                final_parts.append(part[i:i + max_length])
        else:
            final_parts.append(part)
    return final_parts


async def send_long_message(chat_id: int, text: str, context, prefix: str = "", parse_mode=None):
    """Отправляет длинное сообщение по частям"""
    parts = split_message_efficiently(text)
    total_parts = len(parts)
    for i, part in enumerate(parts, 1):
        part_prefix = prefix if total_parts == 1 else f"{prefix}({i}/{total_parts})"
        full_text = part_prefix + "\n" + part if part_prefix else part
        await context.bot.send_message(
            chat_id=chat_id,
            text=full_text,
            parse_mode=parse_mode
        )


def get_calculator_data_safe(context, index: int, default: float = 0.0) -> float:
    """Безопасное получение данных калькулятора из контекста"""
    data = context.user_data.get('calculator_data', {})
    return data.get(index, default)


def generate_hud(session: SkillSession) -> str:
    """Генерация HUD (Heads-Up Display) для SKILLTRAINER"""
    filled = int(session.progress * 10)
    progress_bar = f"[{'█' * filled}{'▒' * (10 - filled)}]"
    hud_lines = [
        f"{progress_bar} {int(session.progress * 100)}%",
        f"Шаг {session.current_step + 1}/{session.max_steps}",
    ]
    if session.selected_mode:
        hud_lines.append(f"Режим: {session.selected_mode.name}")
    if session.gates_passed:
        hud_lines.append(f"Гейты: {len(session.gates_passed)}/{len(SKILLTRAINER_GATES)}")
    return "| ".join(hud_lines)


def generate_hint(session: SkillSession, context: str = "") -> str:
    """Генерация подсказки для пользователя"""
    hints_library = [
        "💡 Совет: Будьте конкретнее в ответах. Вместо 'хочу лучше общаться' попробуйте 'хочу научиться задавать открытые вопросы в диалоге'.",
        "💡 Напоминание: Регулярность важнее длительности. Лучше 15 минут ежедневно, чем 2 часа раз в неделю.",
        "💡 Подсказка: Сфокусируйтесь на одном микро-навыке за раз. Разбейте большую цель на маленькие достижимые шаги.",
        "💡 Идея: Записывайте свои успехи. Даже маленькие победы создают прогресс и мотивацию.",
        "💡 Метод: Используйте технику '5 почему' чтобы докопаться до корня проблемы с навыком."
    ]
    if context and "сложн" in context.lower():
        return "💡 Если сложно: Начните с самого простого действия. Даже 2 минуты практики лучше, чем ничего."
    return random.choice(hints_library)


def check_gate(session: SkillSession, gate_id: str) -> Tuple[bool, str]:
    """Проверка прохождения гейта"""
    gate = SKILLTRAINER_GATES.get(gate_id)
    if not gate:
        return False, "Гейт не найден"
    if gate["validate"](session):
        session.gates_passed.add(gate_id)
        return True, f"✅ {gate['description']}"
    else:
        return False, f"⏳ {gate['description']}"


def format_finish_packet(session: SkillSession, ai_response: str) -> str:
    """Форматирование Finish Packet для SKILLTRAINER"""
    packet = f"""🎓 **FINISH PACKET - SKILLTRAINER {SKILLTRAINER_VERSION}**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📅 Сессия завершена:** {datetime.now().strftime('%d.%m.%Y %H:%M')}
**👤 Пользователь ID:** {session.user_id}
**🎯 Режим тренировки:** {session.selected_mode.name if session.selected_mode else 'Не выбран'}
**📊 Пргресс:** {int(session.progress * 100)}%
**🔍 КЛЮЧЕВЫЕ ОТВЕТЫ:**
"""
    for step, answer in session.answers.items():
        if step < len(SKILLTRAINER_QUESTIONS):
            question_num = SKILLTRAINER_QUESTIONS[step].split('**Шаг')[1].split(':**')[0]
            packet += f"{question_num}: {answer}\n"
    packet += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    packet += f"**🎯 ПЕРСОНАЛИЗИРОВАННАЯ ПРОГРАММА:**\n{ai_response}\n"
    packet += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    packet += f"**📋 ПРОЙДЕННЫЕ ГЕЙТЫ:** {len(session.gates_passed)}/{len(SKILLTRAINER_GATES)}"
    for gate_id in session.gates_passed:
        packet += f"\n✅ {SKILLTRAINER_GATES[gate_id]['description']}"
    return packet

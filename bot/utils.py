"""
Вспомогательные функции бота
"""
import random
import re
from typing import List, Tuple
from datetime import datetime

from .models import SkillSession
from .config import SKILLTRAINER_QUESTIONS, SKILLTRAINER_GATES, SKILLTRAINER_VERSION


def sanitize_user_input(text: str, max_length: int = 2000) -> str:
    """
    Очистка пользовательского ввода от опасных символов
    
    Args:
        text: Входной текст
        max_length: Максимальная длина текста
    
    Returns:
        Очищенный текст
    """
    if not text:
        return ""
    
    # Удаляем потенциально опасные символы
    cleaned = re.sub(r'[<>{}`|\\\-\t]', '', text)
    # Оставляем только безопасные символы
    cleaned = ''.join(char for char in cleaned if char.isprintable() or char in '\n\r')
    
    return cleaned[:max_length]


def split_message_efficiently(text: str, max_length: int = 4096) -> List[str]:
    """
    Разделение длинного сообщения на части для Telegram
    
    Args:
        text: Текст для разделения
        max_length: Максимальная длина части (по умолчанию 4096 для Telegram)
    
    Returns:
        Список частей текста
    """
    if len(text) <= max_length:
        return [text]
    
    # Пытаемся разделить по предложениям
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
    
    # Если некоторые части всё ещё слишком длинные, разбиваем насильно
    final_parts = []
    for part in parts:
        if len(part) > max_length:
            for i in range(0, len(part), max_length):
                final_parts.append(part[i:i + max_length])
        else:
            final_parts.append(part)
    
    return final_parts


def get_calculator_data_safe(context, index: int, default: float = 0.0) -> float:
    """
    Безопасное получение данных калькулятора из контекста
    
    Args:
        context: Контекст пользователя
        index: Индекс данных
        default: Значение по умолчанию
    
    Returns:
        Значение данных или значение по умолчанию
    """
    data = context.user_data.get('calculator_data', {})
    return data.get(index, default)


def generate_hud(session: SkillSession) -> str:
    """
    Генерация HUD (Heads-Up Display) для SKILLTRAINER
    
    Args:
        session: Сессия SKILLTRAINER
    
    Returns:
        Строка HUD
    """
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
    
    return " | ".join(hud_lines)


def generate_hint(session: SkillSession, context: str = "") -> str:
    """
    Генерация подсказки для пользователя
    
    Args:
        session: Сессия SKILLTRAINER
        context: Контекст для персонализации подсказки
    
    Returns:
        Подсказка
    """
    hints_library = [
        "💡 Совет: Будьте конкретнее в ответах. Вместо 'хочу лучше общаться' попробуйте 'хочу научиться задавать открытые вопросы в диалоге'.",
        "💡 Напоминание: Регулярность важнее длительности. Лучше 15 минут ежедневно, чем 2 часа раз в неделю.",
        "💡 Подсказка: Сфокусируйтесь на одном микро-навыке за раз. Разбейте большую цель на маленькие достижимые шаги.",
        "💡 Идея: Записывайте свои успехи. Даже маленькие победы создают прогресс и мотивацию.",
        "💡 Метод: Используйте технику '5 почему' чтобы докопаться до корня проблемы с навыком."
    ]
    
    # Персонализированная подсказка если пользователю сложно
    if context and "сложн" in context.lower():
        return "💡 Если сложно: Начните с самого простого действия. Даже 2 минуты практики лучше, чем ничего."
    
    hint = random.choice(hints_library)
    
    # Ограничиваем длину подсказки
    if len(hint) > 240:
        hint = hint[:237] + "..."
    
    return hint


def check_gate(session: SkillSession, gate_id: str) -> Tuple[bool, str]:
    """
    Проверка прохождения гейта SKILLTRAINER
    
    Args:
        session: Сессия SKILLTRAINER
        gate_id: ID гейта
    
    Returns:
        Кортеж (прошел ли гейт, сообщение)
    """
    if gate_id not in SKILLTRAINER_GATES:
        return False, f"Неизвестный гейт: {gate_id}"
    
    gate = SKILLTRAINER_GATES[gate_id]
    is_passed = gate["validate"](session)
    
    if is_passed:
        session.pass_gate(gate_id)
        return True, f"✅ {gate['description']}"
    else:
        return False, f"⏳ {gate['description']}"


def format_finish_packet(session: SkillSession, ai_response: str) -> str:
    """
    Форматирование Finish Packet для SKILLTRAINER
    
    Args:
        session: Сессия SKILLTRAINER
        ai_response: Ответ AI с персонализированной программой
    
    Returns:
        Отформатированный Finish Packet
    """
    packet = f"""
🎓 **FINISH PACKET - SKILLTRAINER {SKILLTRAINER_VERSION}**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
**📅 Сессия завершена:** {datetime.now().strftime('%d.%m.%Y %H:%M')}
**👤 Пользователь ID:** {session.user_id}
**🎯 Режим тренировки:** {session.selected_mode.name if session.selected_mode else 'Не выбран'}
**📊 Пргресс:** {int(session.progress * 100)}%
**🔍 КЛЮЧЕВЫЕ ОТВЕТЫ:**
"""
    
    # Добавляем ответы пользователя
    for step, answer in session.answers.items():
        if step < len(SKILLTRAINER_QUESTIONS):
            question_num = SKILLTRAINER_QUESTIONS[step].split('**Шаг')[1].split(':**')[0]
            packet += f"\n{question_num}:\n{answer}\n"
    
    packet += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    packet += f"**🎯 ПЕРСОНАЛИЗИРОВАННАЯ ПРОГРАММА:**\n{ai_response}\n"
    packet += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    packet += f"**📋 ПРОЙДЕННЫЕ ГЕЙТЫ:** {len(session.gates_passed)}/{len(SKILLTRAINER_GATES)}\n"
    
    for gate_id in session.gates_passed:
        packet += f"• {SKILLTRAINER_GATES[gate_id]['description']}\n"
    
    if session.last_hint:
        packet += f"\n**💡 ПОСЛЕДНЯЯ ПОДСКАЗКА:**\n• {session.last_hint}\n"
    else:
        packet += f"\n**💡 ПОДСКАЗКИ НЕ ЗАПРАШИВАЛИСЬ**\n"
    
    packet += f"\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    packet += f"**🚀 СЛЕДУЮЩИЕ ШАГИ:**\n"
    packet += f"1. Повторите основные техники в течение недели\n"
    packet += f"2. Отметьте 3 ситуации, где применили навык\n"
    packet += f"3. Вернитесь через 7 дней для оценки прогресса\n"
    
    return packet

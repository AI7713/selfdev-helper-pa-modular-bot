from typing import Dict, Any

def generate_hud(agent_name: str, session_data: Dict[str, Any]) -> str:
    """
    Генерирует HUD (Heads-Up Display) для агента.
    Пример: [█████▁▁▁▁▁] 50% | Блок: B1.b | Эксперты: 2
    """
    current = session_data.get('current_block', 'B0')
    experts = len(session_data.get('experts', []))
    progress = _estimate_progress(current)
    bar = _make_progress_bar(progress)
    return f"{bar} {progress}% | Блок: {current} | Эксперты: {experts}"

def _estimate_progress(block_id: str) -> int:
    """Простая эвристика прогресса по ID блока"""
    if block_id.startswith('B'):
        try:
            num = int(block_id[1:].split('.')[0])
            return min(100, max(0, int(num * 12)))
        except:
            return 0
    elif block_id.startswith('Ω'):
        return 95
    return 0

def _make_progress_bar(pct: int) -> str:
    filled = pct // 10
    bar = '█' * filled + '▁' * (10 - filled)
    return f"[{bar}]"

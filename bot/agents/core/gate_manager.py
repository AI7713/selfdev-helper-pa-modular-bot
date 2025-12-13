from typing import Dict, Any, Tuple

class GateManager:
    """
    Управляет проверкой гейтов (DOD — Definition of Done).
    """
    def __init__(self, gate_rules: Dict[str, Any]):
        self.gate_rules = gate_rules  # из YAML

    def check_gate(self, block_id: str, session_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Проверяет, пройден ли гейт для блока.
        Возвращает (успешно, сообщение).
        """
        gate_config = self.gate_rules.get(block_id, {})
        if not gate_config:
            return True, "Гейт не требуется"

        # Пример простой проверки: все поля из required_fields заполнены
        required_fields = gate_config.get('required_fields', [])
        for field in required_fields:
            if field not in session_data or not session_data[field]:
                return False, f"Требуется заполнить: {field}"

        # Можно добавить кастомную логику в будущем
        return True, "✅ Гейт пройден"

from typing import Dict, List, Any
import yaml
import os

class StateMachine:
    """
    Загружает YAML-конфиг и управляет переходами между блоками.
    """
    def __init__(self, config_path: str):
        self.config = self._load_config(config_path)
        self.blocks = self.config.get('blocks', {})
        self.transitions = self.config.get('transitions', {})
        self.gate_blocks = set(self.config.get('gated_blocks', []))

    def _load_config(self, path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Конфиг не найден: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def get_next_blocks(self, current_block: str) -> List[str]:
        """Возвращает возможные следующие блоки из текущего"""
        return self.transitions.get(current_block, [])

    def is_gated(self, block_id: str) -> bool:
        """Проверяет, требует ли блок прохождения гейта"""
        return block_id in self.gate_blocks

    def get_block_config(self, block_id: str) -> Dict[str, Any]:
        """Возвращает конфигурацию блока"""
        return self.blocks.get(block_id, {})

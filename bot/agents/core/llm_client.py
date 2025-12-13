"""
Единая точка вызова LLM для UAF-агентов.
Поддерживает кэширование, маскировку ПДн и централизованную безопасность.
"""
from typing import Optional
import hashlib
from bot.utils import mask_pii  # ← правильно: импорт из корневого пакета bot
from bot.models import ai_cache  # ← используем общий кэш из models.py


class LLMClient:
    """
    Единая точка вызова LLM с обязательной фильтрацией ПДн и поддержкой кэширования.
    """
    def __init__(self, groq_client):
        self.groq_client = groq_client

    async def call_llm(
        self,
        system_prompt: str,
        user_query: str,
        model: str = "llama-3.1-8b-instant",
        max_tokens: int = 2000
    ) -> Optional[str]:
        """
        Вызывает Groq с предварительной маскировкой ПДн и кэшированием ответа.
        Использует глобальный `ai_cache` из `models.py` для совместимости с остальным ботом.
        """
        # 🔒 МАСКИРОВКА ПДн — ОБЯЗАТЕЛЬНА
        clean_query = mask_pii(user_query)

        # 🔥 ИСПОЛЬЗУЕМ ГЛОБАЛЬНЫЙ КЭШ (как в ai_handlers.py)
        cache_key = ai_cache.get_cache_key("orchestrator", clean_query)
        cached_response = ai_cache.get_cached_response("orchestrator", clean_query)
        if cached_response:
            return cached_response

        try:
            response = self.groq_client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": clean_query}
                ],
                model=model,
                max_tokens=max_tokens,
                temperature=0.7
            )
            result = response.choices[0].message.content

            # Сохраняем в общий кэш
            ai_cache.cache_response("orchestrator", clean_query, result)
            return result

        except Exception as e:
            print(f"LLMClient error: {e}")
            return None

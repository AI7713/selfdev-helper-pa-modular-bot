from typing import Optional
import hashlib
from ..utils import mask_pii  # ← используем СУЩЕСТВУЮЩУЮ функцию из bot/utils.py

class LLMClient:
    """
    Единая точка вызова LLM с обязательной фильтрацией ПДн.
    """
    def __init__(self, groq_client):
        self.groq_client = groq_client
        self._cache = {}

    async def call_llm(
        self,
        system_prompt: str,
        user_query: str,
        model: str = "llama-3.1-8b-instant",
        max_tokens: int = 2000
    ) -> Optional[str]:
        """
        Вызывает Groq с предварительной маскировкой ПДн.
        """
        # 🔒 МАСКИРОВКА ПДн — ОБЯЗАТЕЛЬНА
        clean_query = mask_pii(user_query)

        # Кэширование (опционально)
        cache_key = hashlib.md5(f"{system_prompt}:{clean_query}".encode()).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]

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
            self._cache[cache_key] = result
            return result
        except Exception as e:
            print(f"LLMClient error: {e}")
            return None

# bot/agents/core/llm_client.py
from typing import Optional
from bot.utils import mask_pii
from bot.models import ai_cache

class LLMClient:
    def __init__(self, groq_client):
        self.groq_client = groq_client

    async def call_llm(
        self,
        system_prompt: str,
        user_query: str,
        model: str = "llama-3.1-8b-instant",
        max_tokens: int = 2000
    ) -> Optional[str]:
        clean_query = mask_pii(user_query)

        # ✅ ИСПОЛЬЗУЕМ ГЛОБАЛЬНЫЙ КЭШ ИЗ MODELS.PY
        if cached := ai_cache.get_cached_response("orchestrator", clean_query):
            return cached

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
            ai_cache.cache_response("orchestrator", clean_query, result)  # ✅ Сохраняем
            return result
        except Exception as e:
            print(f"LLMClient error: {e}")
            return None

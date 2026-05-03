"""
posting/llm.py — Обращение к LLM (g4f) для переработки текста поста.
"""
import asyncio
import logging

from g4f.client import Client

logger = logging.getLogger(__name__)


async def clean_text_with_llm(input_text: str, prompt_template: str) -> str:
    """
    Передаёт текст в LLM и возвращает очищенный вариант.
    При любой ошибке возвращает исходный текст.
    """
    if not input_text:
        return ""

    if "{text}" not in prompt_template:
        prompt_template += "\nТекст:\n{text}\n\nОтветь только готовым текстом поста."

    system = (
        "Ты редактор Telegram-канала. "
        "Всегда возвращай только готовый текст поста для публикации, "
        "без пояснений, без оформления, только результат."
    )

    try:
        client = Client()
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt_template.format(text=input_text)},
            ],
        )
        result = response.choices[0].message.content.strip()
        return result if result else input_text
    except Exception as exc:
        logger.error("[LLM] Ошибка: %s", exc)
        return input_text

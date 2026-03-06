# -*- coding: utf-8 -*-
"""
Клиент для взаимодействия с LLM через OpenRouter API.
Использует aiohttp для асинхронных запросов.
"""

import logging
from typing import Optional

import aiohttp

import config
import prompts

logger = logging.getLogger(__name__)


async def ask(
    user_message: str,
    system_message: str = prompts.SYSTEM_ANALYST,
    model: Optional[str] = None,
) -> str:
    """
    Отправляет запрос к LLM и возвращает текст ответа.

    Args:
        user_message: сообщение пользователя / промпт
        system_message: системный промпт
        model: модель (по умолчанию из config.PROVIDER_MODEL)

    Returns:
        Текст ответа модели или сообщение об ошибке.
    """
    model = model or config.PROVIDER_MODEL
    headers = {
        "Authorization": f"Bearer {config.PROVIDER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/redalbum/AI_agent_1-",
        "X-Title": "AI Бизнес-Ассистент для 1С",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_message},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.3,
        "max_tokens": 2000,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{config.PROVIDER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("LLM вернул статус %d: %s", resp.status, body[:200])
                    return f"❌ Ошибка LLM (статус {resp.status}). Проверьте PROVIDER_API_KEY."
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
    except aiohttp.ClientConnectorError:
        logger.error("Нет подключения к интернету или LLM недоступен")
        return "❌ Нет соединения с LLM. Проверьте подключение к интернету."
    except Exception as exc:
        logger.error("Ошибка LLM-запроса: %s", exc)
        return f"❌ Ошибка при обращении к LLM: {exc}"

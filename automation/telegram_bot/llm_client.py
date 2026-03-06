# -*- coding: utf-8 -*-
"""
Асинхронный клиент для LLM (OpenRouter / любой OpenAI-совместимый API).
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)


class LLMClient:
    """Клиент для обращения к LLM через OpenAI-совместимый API."""

    def __init__(self, base_url: str, api_key: str, model: str, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Возвращает существующую сессию или создаёт новую."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        return self._session

    async def close(self) -> None:
        """Закрывает HTTP-сессию."""
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def analyze(self, system_prompt: str, user_message: str) -> str:
        """
        Отправляет запрос к LLM и возвращает текстовый ответ.

        Args:
            system_prompt: Системный промпт.
            user_message: Сообщение пользователя / данные для анализа.

        Returns:
            Текст ответа LLM.
        """
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}/chat/completions"
        try:
            session = await self._get_session()
            async with session.post(url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data["choices"][0]["message"]["content"]
        except aiohttp.ClientResponseError as exc:
            logger.error("LLM HTTP error %s: %s", exc.status, exc.message)
            raise
        except Exception as exc:
            logger.error("LLM request failed: %s", exc)
            raise

    async def generate_query(self, user_request: str, metadata_context: str) -> str:
        """
        Генерирует запрос на языке 1С по запросу пользователя.

        Args:
            user_request: Запрос пользователя на естественном языке.
            metadata_context: JSON-строка с метаданными базы.

        Returns:
            Текст запроса 1С.
        """
        from .prompts import SYSTEM_PROMPT_QUERY_GENERATOR

        system = SYSTEM_PROMPT_QUERY_GENERATOR.format(metadata=metadata_context)
        return await self.analyze(system, user_request)

    async def analyze_data(self, data: str, metadata_context: str) -> str:
        """
        Анализирует данные из 1С и возвращает бизнес-рекомендации.

        Args:
            data: Строковое представление данных из 1С.
            metadata_context: JSON-строка с метаданными базы.

        Returns:
            Текст анализа и рекомендаций.
        """
        from .prompts import SYSTEM_PROMPT_ANALYZER

        system = SYSTEM_PROMPT_ANALYZER.format(metadata=metadata_context)
        return await self.analyze(system, data)

    async def analyze_metadata(self, metadata_json: str) -> dict:
        """
        Анализирует схему метаданных 1С и возвращает словарь возможностей.

        Args:
            metadata_json: JSON-строка со схемой метаданных.

        Returns:
            Словарь с ключами analytics, inventory, finance, summary.
        """
        from .prompts import SYSTEM_PROMPT_METADATA_ANALYST

        system = SYSTEM_PROMPT_METADATA_ANALYST
        response = await self.analyze(system, metadata_json)
        try:
            # Попытка извлечь JSON из ответа
            start = response.find("{")
            end = response.rfind("}") + 1
            if start != -1 and end > start:
                return json.loads(response[start:end])
        except Exception:
            pass
        return {"summary": response, "analytics": [], "inventory": [], "finance": []}

# -*- coding: utf-8 -*-
"""
Сканер метаданных 1С.
При первом запуске подключается к базе, обходит объекты метаданных,
сохраняет схему в JSON-кеш. LLM анализирует схему и определяет возможности.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# Ключевые типы объектов, которые мы сканируем (без полного обхода всех реквизитов)
_KEY_OBJECT_TYPES = [
    "Справочник",
    "Документ",
    "РегистрНакопления",
    "РегистрСведений",
]

# Ограничение: не более N объектов каждого типа для полного сканирования реквизитов
_MAX_OBJECTS_WITH_FIELDS = 20


class MetadataScanner:
    """Сканирует метаданные базы 1С и кеширует результат."""

    def __init__(self, connector, llm_client=None) -> None:
        """
        Args:
            connector: Экземпляр OneCConnector.
            llm_client: Экземпляр LLMClient (опционально, для анализа возможностей).
        """
        self._connector = connector
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def scan_metadata(self) -> dict:
        """
        Сканирует метаданные базы 1С.

        Returns:
            Словарь схемы метаданных.
        """
        logger.info("Начало сканирования метаданных 1С…")
        schema: dict = {
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "objects": {},
        }
        try:
            all_objects = await self._connector.get_metadata()
        except Exception as exc:
            logger.error("Ошибка получения списка объектов: %s", exc)
            return schema

        # Группируем по типу
        by_type: dict[str, list[str]] = {}
        for obj_full_name in all_objects:
            if "." not in obj_full_name:
                continue
            obj_type, obj_name = obj_full_name.split(".", 1)
            by_type.setdefault(obj_type, []).append(obj_name)

        schema["objects_list"] = by_type

        # Детальное сканирование реквизитов для ключевых типов
        fields_map: dict[str, dict[str, list[str]]] = {}
        for obj_type in _KEY_OBJECT_TYPES:
            names = by_type.get(obj_type, [])
            fields_map[obj_type] = {}
            for name in names[:_MAX_OBJECTS_WITH_FIELDS]:
                try:
                    fields = await self._connector.get_object_fields(obj_type, name)
                    fields_map[obj_type][name] = fields
                except Exception:
                    fields_map[obj_type][name] = []

        schema["fields"] = fields_map
        logger.info(
            "Сканирование завершено. Объектов: %d",
            sum(len(v) for v in by_type.values()),
        )
        return schema

    async def get_object_fields(self, obj_type: str, obj_name: str) -> dict:
        """
        Получает поля конкретного объекта.

        Returns:
            Словарь {obj_type: {obj_name: [field, ...]}}
        """
        fields = await self._connector.get_object_fields(obj_type, obj_name)
        return {obj_type: {obj_name: fields}}

    def save_cache(self, filepath: str, data: dict) -> None:
        """Сохраняет схему метаданных в JSON-файл."""
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info("Кеш метаданных сохранён: %s", filepath)
        except Exception as exc:
            logger.error("Ошибка сохранения кеша: %s", exc)

    def load_cache(self, filepath: str) -> Optional[dict]:
        """
        Загружает схему из кеша.

        Returns:
            Словарь или None если файл не найден / повреждён.
        """
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as exc:
            logger.error("Ошибка загрузки кеша: %s", exc)
            return None

    def is_cache_valid(self, cache_data: dict, ttl_hours: int) -> bool:
        """
        Проверяет актуальность кеша по времени сканирования.

        Args:
            cache_data: Словарь кеша.
            ttl_hours: Время жизни кеша в часах.

        Returns:
            True если кеш актуален.
        """
        scanned_at_str = cache_data.get("scanned_at")
        if not scanned_at_str:
            return False
        try:
            scanned_at = datetime.fromisoformat(scanned_at_str)
            age_hours = (
                datetime.now(timezone.utc) - scanned_at
            ).total_seconds() / 3600
            return age_hours < ttl_hours
        except Exception:
            return False

    async def analyze_capabilities(self, metadata: dict) -> dict:
        """
        Использует LLM для анализа схемы метаданных и определения возможностей бота.

        Args:
            metadata: Словарь схемы метаданных.

        Returns:
            Словарь возможностей {analytics, inventory, finance, summary}.
        """
        if self._llm is None:
            return {
                "summary": "LLM недоступен — анализ возможностей не выполнен.",
                "analytics": [],
                "inventory": [],
                "finance": [],
            }
        # Передаём только объекты (без полей) для краткости
        compact = {
            "objects_list": metadata.get("objects_list", {}),
            "scanned_at": metadata.get("scanned_at", ""),
        }
        try:
            return await self._llm.analyze_metadata(json.dumps(compact, ensure_ascii=False))
        except Exception as exc:
            logger.error("Ошибка LLM-анализа метаданных: %s", exc)
            return {
                "summary": f"Ошибка анализа: {exc}",
                "analytics": [],
                "inventory": [],
                "finance": [],
            }

    def metadata_summary_text(self, metadata: dict) -> str:
        """Возвращает краткий текст с описанием схемы для промптов."""
        objects_list = metadata.get("objects_list", {})
        lines = []
        for obj_type, names in objects_list.items():
            lines.append(f"{obj_type}: {', '.join(names[:10])}" + (" …" if len(names) > 10 else ""))
        return "\n".join(lines) if lines else "Метаданные не загружены."

# -*- coding: utf-8 -*-
"""
Сканер метаданных базы 1С.

При первом запуске подключается к базе, получает список объектов метаданных
(документы, справочники, регистры накопления) и сохраняет описание в JSON-файл.
Повторные запуски читают данные из кеша (если не истёк TTL).
"""

import json
import logging
import os
import time
from typing import Optional

import config
import onec_connector

logger = logging.getLogger(__name__)

# Ключи, которые ищем в метаданных для определения возможностей базы
_SALES_HINTS = {"продажи", "реализация", "чеки", "розница"}
_INVENTORY_HINTS = {"остатки", "товары", "склад", "номенклатура"}
_FINANCE_HINTS = {"касса", "деньги", "оплата", "финансы", "выручка"}


class MetadataCache:
    """Хранит описание метаданных базы и результат LLM-анализа возможностей."""

    def __init__(self):
        self.documents: list[dict] = []
        self.catalogs: list[dict] = []
        self.accumulation_registers: list[dict] = []
        self.capabilities: dict[str, bool] = {
            "sales": False,
            "inventory": False,
            "finance": False,
        }
        self.scanned_at: float = 0.0

    def is_fresh(self) -> bool:
        ttl_seconds = config.METADATA_CACHE_TTL_HOURS * 3600
        return (time.time() - self.scanned_at) < ttl_seconds

    def to_dict(self) -> dict:
        return {
            "documents": self.documents,
            "catalogs": self.catalogs,
            "accumulation_registers": self.accumulation_registers,
            "capabilities": self.capabilities,
            "scanned_at": self.scanned_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MetadataCache":
        obj = cls()
        obj.documents = data.get("documents", [])
        obj.catalogs = data.get("catalogs", [])
        obj.accumulation_registers = data.get("accumulation_registers", [])
        obj.capabilities = data.get("capabilities", obj.capabilities)
        obj.scanned_at = data.get("scanned_at", 0.0)
        return obj

    def summary_text(self) -> str:
        """Краткое текстовое описание для передачи в LLM-промпт."""
        lines = []
        if self.documents:
            names = ", ".join(d["name"] for d in self.documents[:10])
            lines.append(f"Документы: {names}")
        if self.catalogs:
            names = ", ".join(c["name"] for c in self.catalogs[:10])
            lines.append(f"Справочники: {names}")
        if self.accumulation_registers:
            names = ", ".join(r["name"] for r in self.accumulation_registers[:10])
            lines.append(f"Регистры накопления: {names}")
        caps = [k for k, v in self.capabilities.items() if v]
        if caps:
            cap_map = {"sales": "продажи", "inventory": "склад", "finance": "финансы"}
            lines.append("Доступные возможности: " + ", ".join(cap_map.get(c, c) for c in caps))
        return "\n".join(lines) if lines else "Метаданные не загружены"


_cache: Optional[MetadataCache] = None


def _load_from_file() -> Optional[MetadataCache]:
    path = config.METADATA_CACHE_FILE
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return MetadataCache.from_dict(data)
    except Exception as exc:
        logger.warning("Не удалось прочитать кеш метаданных: %s", exc)
        return None


def _save_to_file(cache: MetadataCache) -> None:
    path = config.METADATA_CACHE_FILE
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cache.to_dict(), f, ensure_ascii=False, indent=2)
        logger.info("Кеш метаданных сохранён в %s", path)
    except Exception as exc:
        logger.warning("Не удалось сохранить кеш метаданных: %s", exc)


def _detect_capabilities(cache: MetadataCache) -> None:
    """Определяет возможности базы по именам объектов."""
    all_names = [obj["name"].lower() for obj in cache.documents + cache.catalogs + cache.accumulation_registers]

    def has_hint(hints: set) -> bool:
        return any(hint in name for name in all_names for hint in hints)

    cache.capabilities["sales"] = has_hint(_SALES_HINTS)
    cache.capabilities["inventory"] = has_hint(_INVENTORY_HINTS)
    cache.capabilities["finance"] = has_hint(_FINANCE_HINTS)


def _get_metadata_names(com_obj, collection_attr: str) -> list[dict]:
    """Получает список объектов из коллекции метаданных 1С."""
    result = []
    try:
        meta = getattr(com_obj, "Метаданные", None)
        if meta is None:
            return result
        collection = getattr(meta, collection_attr, None)
        if collection is None:
            return result
        count = getattr(collection, "Количество", None)
        if callable(count):
            n = count()
        else:
            return result
        for i in range(n):
            try:
                obj = collection.Получить(i)
                name = getattr(obj, "Имя", None)
                synonym = getattr(obj, "Синоним", None)
                if name:
                    result.append({
                        "name": str(name),
                        "synonym": str(synonym) if synonym else str(name),
                    })
            except Exception:
                pass
    except Exception as exc:
        logger.debug("Не удалось получить метаданные (%s): %s", collection_attr, exc)
    return result


def scan(com_obj) -> MetadataCache:
    """
    Сканирует метаданные базы 1С и возвращает заполненный MetadataCache.
    Результат сохраняется в файл кеша.
    """
    logger.info("Сканирую метаданные базы 1С...")
    cache = MetadataCache()
    cache.documents = _get_metadata_names(com_obj, "Документы")
    cache.catalogs = _get_metadata_names(com_obj, "Справочники")
    cache.accumulation_registers = _get_metadata_names(com_obj, "РегистрыНакопления")
    _detect_capabilities(cache)
    cache.scanned_at = time.time()
    logger.info(
        "Найдено: %d документов, %d справочников, %d регистров накопления",
        len(cache.documents), len(cache.catalogs), len(cache.accumulation_registers),
    )
    _save_to_file(cache)
    return cache


def get_or_scan(com_obj=None) -> MetadataCache:
    """
    Возвращает MetadataCache из памяти/файла или сканирует базу заново.

    Args:
        com_obj: COM-объект соединения с 1С (нужен только при сканировании).
    """
    global _cache

    # Проверяем кеш в памяти
    if _cache is not None and _cache.is_fresh():
        return _cache

    # Пробуем загрузить с диска
    cached = _load_from_file()
    if cached is not None and cached.is_fresh():
        _cache = cached
        return _cache

    # Сканируем базу
    if com_obj is None:
        com_obj = onec_connector.connect(
            config.ONEC_CONNECTION_STRING,
            config.ONEC_USER,
            config.ONEC_PASSWORD,
        )

    if com_obj is None:
        # Возвращаем пустой кеш, чтобы бот не падал
        _cache = MetadataCache()
        return _cache

    _cache = scan(com_obj)
    return _cache

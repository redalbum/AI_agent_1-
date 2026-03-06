# -*- coding: utf-8 -*-
"""
Обёртка для подключения к 1С через COM.
Использует существующий пакет com_1c из automation/.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Добавляем каталог automation в path, чтобы импортировать com_1c
_telegram_bot_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_telegram_bot_dir)
if _automation_dir not in sys.path:
    sys.path.insert(0, _automation_dir)

try:
    from com_1c import (
        connect_to_1c,
        execute_query,
        safe_getattr,
    )
    _COM_AVAILABLE = True
except ImportError:
    _COM_AVAILABLE = False
    logger.warning("Пакет com_1c не найден — COM-подключение к 1С недоступно.")


class OneCConnector:
    """Обёртка для синхронного COM-подключения к 1С, вызываемого из async-кода."""

    def __init__(self, connection_string: str, user: str = "Администратор", password: str = "") -> None:
        self.connection_string = connection_string
        self.user = user
        self.password = password
        self._conn = None

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    async def connect(self) -> bool:
        """
        Устанавливает COM-соединение с 1С.

        Returns:
            True при успехе, False при ошибке.
        """
        if not _COM_AVAILABLE:
            logger.error("com_1c недоступен.")
            return False
        try:
            conn_str = self._build_connection_string()
            self._conn = await asyncio.to_thread(connect_to_1c, conn_str)
            return self._conn is not None
        except Exception as exc:
            logger.error("Ошибка подключения к 1С: %s", exc)
            return False

    async def execute_query(self, query_text: str, columns: list[str] | None = None) -> list[dict]:
        """
        Выполняет запрос 1С и возвращает список строк.

        Args:
            query_text: Текст запроса на языке 1С.
            columns: Список имён колонок результата. Если None, пытается
                     определить автоматически из текста запроса.

        Returns:
            Список словарей — строк результата.
        """
        if self._conn is None:
            raise RuntimeError("Нет подключения к 1С. Вызовите connect() сначала.")
        if columns is None:
            columns = self._extract_columns(query_text)
        return await asyncio.to_thread(
            execute_query, self._conn, query_text, columns
        )

    async def get_metadata(self, filter_prefix: str = "") -> list[str]:
        """
        Возвращает список имён объектов метаданных 1С.

        Args:
            filter_prefix: Необязательный префикс для фильтрации (напр. "Справочник").

        Returns:
            Список строк вида "ТипОбъекта.Имя".
        """
        if self._conn is None:
            raise RuntimeError("Нет подключения к 1С.")
        return await asyncio.to_thread(self._sync_get_metadata, filter_prefix)

    async def get_object_fields(self, obj_type: str, obj_name: str) -> list[str]:
        """
        Возвращает список имён реквизитов объекта метаданных.

        Args:
            obj_type: Тип объекта (напр. "Справочники", "Документы").
            obj_name: Имя объекта (напр. "Номенклатура").

        Returns:
            Список имён полей / реквизитов.
        """
        if self._conn is None:
            raise RuntimeError("Нет подключения к 1С.")
        return await asyncio.to_thread(self._sync_get_object_fields, obj_type, obj_name)

    async def disconnect(self) -> None:
        """Закрывает COM-соединение."""
        if self._conn is not None:
            try:
                await asyncio.to_thread(self._sync_disconnect)
            except Exception:
                pass
            self._conn = None

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    # ------------------------------------------------------------------
    # Синхронные вспомогательные методы (выполняются в отдельном потоке)
    # ------------------------------------------------------------------

    def _build_connection_string(self) -> str:
        """Добавляет пользователя и пароль к строке подключения при необходимости."""
        conn = self.connection_string
        # Sanitize: remove semicolons from user/password to avoid injection
        safe_user = self.user.replace(";", "") if self.user else ""
        safe_password = self.password.replace(";", "") if self.password else ""
        if safe_user and "Usr=" not in conn:
            conn = conn.rstrip(";") + f";Usr={safe_user};"
        if safe_password and "Pwd=" not in conn:
            conn = conn.rstrip(";") + f"Pwd={safe_password};"
        return conn

    def _sync_get_metadata(self, filter_prefix: str) -> list[str]:
        """Синхронный обход метаданных через COM."""
        result = []
        meta_collections = {
            "Справочники": "Справочник",
            "Документы": "Документ",
            "РегистрыНакопления": "РегистрНакопления",
            "РегистрыСведений": "РегистрСведений",
            "РегистрыБухгалтерии": "РегистрБухгалтерии",
            "ПланыВидовХарактеристик": "ПланВидовХарактеристик",
            "ПланыСчетов": "ПланСчетов",
        }
        metadata_obj = safe_getattr(self._conn, "Метаданные", None)
        if metadata_obj is None:
            return result
        for collection_name, obj_type in meta_collections.items():
            if filter_prefix and not obj_type.startswith(filter_prefix):
                continue
            collection = safe_getattr(metadata_obj, collection_name, None)
            if collection is None:
                continue
            try:
                count = safe_getattr(collection, "Количество", None)
                if callable(count):
                    count = count()
                if count is None:
                    continue
                for i in range(int(count)):
                    try:
                        item = collection.Получить(i)
                        name = safe_getattr(item, "Имя", None)
                        if name:
                            result.append(f"{obj_type}.{name}")
                    except Exception:
                        continue
            except Exception:
                continue
        return result

    def _sync_get_object_fields(self, obj_type: str, obj_name: str) -> list[str]:
        """Синхронное получение реквизитов объекта метаданных."""
        fields = []
        # Маппинг типа объекта на коллекцию метаданных
        type_to_collection = {
            "Справочник": "Справочники",
            "Документ": "Документы",
            "РегистрНакопления": "РегистрыНакопления",
            "РегистрСведений": "РегистрыСведений",
        }
        collection_name = type_to_collection.get(obj_type)
        if not collection_name:
            return fields
        metadata_obj = safe_getattr(self._conn, "Метаданные", None)
        if metadata_obj is None:
            return fields
        collection = safe_getattr(metadata_obj, collection_name, None)
        if collection is None:
            return fields
        obj_meta = safe_getattr(collection, obj_name, None)
        if obj_meta is None:
            return fields
        # Стандартные реквизиты
        for attr_collection in ("Реквизиты", "СтандартныеРеквизиты"):
            attr_coll = safe_getattr(obj_meta, attr_collection, None)
            if attr_coll is None:
                continue
            try:
                count = safe_getattr(attr_coll, "Количество", None)
                if callable(count):
                    count = count()
                for i in range(int(count)):
                    try:
                        attr = attr_coll.Получить(i)
                        name = safe_getattr(attr, "Имя", None)
                        if name:
                            fields.append(str(name))
                    except Exception:
                        continue
            except Exception:
                continue
        return fields

    def _sync_disconnect(self) -> None:
        """Попытка корректно закрыть COM-соединение."""
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass

    @staticmethod
    def _extract_columns(query_text: str) -> list[str]:
        """
        Пытается извлечь имена колонок из текста запроса 1С.
        Возвращает пустой список, если не удалось.
        """
        import re
        # Ищем "КАК <ИмяКолонки>" в тексте запроса
        aliases = re.findall(r"\bКАК\s+(\w+)", query_text, re.IGNORECASE)
        if aliases:
            return aliases
        # Если нет КАК, ищем имена полей после ВЫБРАТЬ
        select_match = re.search(r"ВЫБРАТЬ[^,\n]*(.*?)ИЗ", query_text, re.DOTALL | re.IGNORECASE)
        if select_match:
            fields_part = select_match.group(1)
            names = re.findall(r"\.(\w+)(?:\s*,|\s*$)", fields_part)
            return names
        return []

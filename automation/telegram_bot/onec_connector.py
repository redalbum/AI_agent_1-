# -*- coding: utf-8 -*-
"""
Обёртка над COM-подключением к 1С.
Повторно использует логику из automation/com_1c/com_connector.py,
адаптированную для нужд Telegram-бота.
"""

import sys
import logging

logger = logging.getLogger(__name__)

try:
    import win32com.client
    import pythoncom
    _WIN32_AVAILABLE = True
except ImportError:
    _WIN32_AVAILABLE = False


def is_windows() -> bool:
    return sys.platform == "win32"


def connect(connection_string: str, user: str = "", password: str = ""):
    """
    Подключиться к базе 1С через COM.

    Args:
        connection_string: строка подключения (File="..."; или Srvr=...;Ref=...;)
        user: пользователь 1С
        password: пароль пользователя 1С

    Returns:
        COM-объект соединения или None при ошибке.
    """
    if not is_windows():
        logger.error("COM-подключение к 1С доступно только на Windows")
        return None

    if not _WIN32_AVAILABLE:
        logger.error(
            "Модуль pywin32 не установлен. Выполните: pip install pywin32"
        )
        return None

    try:
        pythoncom.CoInitialize()
    except Exception:
        pass

    # Добавляем пользователя/пароль в строку подключения, если не указаны явно
    conn_str = _inject_credentials(connection_string, user, password)

    for progid in ("V85.COMConnector", "V83.COMConnector", "V82.COMConnector"):
        try:
            connector = win32com.client.Dispatch(progid)
            com_object = connector.Connect(conn_str)
            logger.info("Подключение к 1С успешно (%s)", progid)
            return com_object
        except Exception as exc:
            logger.debug("Не удалось подключиться через %s: %s", progid, exc)

    logger.error(
        "Не удалось подключиться к базе 1С. "
        "Проверьте ONEC_CONNECTION_STRING и убедитесь, что платформа 1С установлена."
    )
    return None


def _inject_credentials(connection_string: str, user: str, password: str) -> str:
    """Добавляет Usr= и Pwd= в строку подключения, если их нет."""
    cs = connection_string.rstrip(";")
    if "Usr=" not in cs and user:
        cs += f';Usr="{user}"'
    if "Pwd=" not in cs:
        cs += f';Pwd="{password}"'
    return cs + ";"


def execute_query(com_object, query_text: str, columns: list[str], params: dict | None = None) -> list[dict]:
    """
    Выполняет запрос 1С и возвращает список словарей.

    Args:
        com_object: COM-объект соединения
        query_text: текст запроса на языке 1С
        columns: список имён колонок результата
        params: словарь параметров запроса

    Returns:
        Список словарей {имя_колонки: значение}
    """
    try:
        query = com_object.NewObject("Запрос")
        query.Текст = query_text
        if params:
            for name, value in params.items():
                query.УстановитьПараметр(name, value)
        result = query.Выполнить()
        selection = result.Выбрать()
        rows = []
        while selection.Следующий():
            row = {}
            for col in columns:
                try:
                    value = getattr(selection, col, None)
                    row[col] = _to_python(value)
                except Exception:
                    row[col] = ""
            rows.append(row)
        return rows
    except Exception as exc:
        logger.error("Ошибка выполнения запроса 1С: %s", exc)
        return []


def _to_python(value):
    """Преобразует COM-значение в базовый тип Python."""
    if value is None:
        return ""
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            return f"{value.year:04d}-{value.month:02d}-{value.day:02d}"
        except Exception:
            pass
    if hasattr(value, "_oleobj_"):
        try:
            s = str(value)
            if "<COMObject" in s:
                return ""
            return s
        except Exception:
            return ""
    return value

# -*- coding: utf-8 -*-
"""
Загрузка конфигурации из .env файла.
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _get_required(key: str) -> str:
    value = os.getenv(key, "").strip()
    if not value:
        raise ValueError(f"Не задана обязательная переменная окружения: {key}")
    return value


def _get_optional(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# Telegram
TELEGRAM_BOT_TOKEN: str = _get_required("TELEGRAM_BOT_TOKEN")

_raw_users = _get_required("TELEGRAM_ALLOWED_USERS")
TELEGRAM_ALLOWED_USERS: list[int] = [
    int(uid.strip()) for uid in _raw_users.split(",") if uid.strip().lstrip("-").isdigit()
]

# 1С
ONEC_CONNECTION_STRING: str = _get_required("ONEC_CONNECTION_STRING")
ONEC_USER: str = _get_optional("ONEC_USER", "Администратор")
ONEC_PASSWORD: str = _get_optional("ONEC_PASSWORD", "")

# LLM
PROVIDER_BASE_URL: str = _get_optional("PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
PROVIDER_API_KEY: str = _get_required("PROVIDER_API_KEY")
PROVIDER_MODEL: str = _get_optional("PROVIDER_MODEL", "deepseek/deepseek-chat")

# Кеш метаданных
METADATA_CACHE_FILE: str = _get_optional("METADATA_CACHE_FILE", "metadata_cache.json")
METADATA_CACHE_TTL_HOURS: int = int(_get_optional("METADATA_CACHE_TTL_HOURS", "24"))

# Логирование
LOG_LEVEL: str = _get_optional("LOG_LEVEL", "INFO")

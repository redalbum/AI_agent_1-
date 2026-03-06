# -*- coding: utf-8 -*-
"""
Конфигурация Telegram-бота бизнес-ассистента 1С.
Загружает настройки из переменных окружения / .env файла.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Telegram
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Список разрешённых user_id через запятую; пусто — доступ для всех
_allowed_raw = os.getenv("TELEGRAM_ALLOWED_USERS", "")
TELEGRAM_ALLOWED_USERS: list[int] = []
if _allowed_raw.strip():
    for _uid in _allowed_raw.split(","):
        _uid = _uid.strip()
        if _uid:
            try:
                TELEGRAM_ALLOWED_USERS.append(int(_uid))
            except ValueError:
                raise ValueError(
                    f"Некорректный user_id в TELEGRAM_ALLOWED_USERS: '{_uid}'. "
                    "Укажите числовые Telegram user_id через запятую."
                )

# 1C Connection
# Поддерживается новое имя ONEC_BASE_PATH (путь к папке базы)
# и старое ONEC_CONNECTION_STRING для обратной совместимости.
ONEC_BASE_PATH: str = os.getenv("ONEC_BASE_PATH", "")
ONEC_CONNECTION_STRING: str = os.getenv(
    "ONEC_CONNECTION_STRING",
    os.getenv(
        "1C_CONNECTION_STRING",
        f'File="{ONEC_BASE_PATH}";' if ONEC_BASE_PATH else "",
    ),
)
ONEC_USER: str = os.getenv("ONEC_USER", "")
ONEC_PASSWORD: str = os.getenv("ONEC_PASSWORD", "")

# LLM (OpenRouter / any OpenAI-compatible)
# Поддерживаются новые имена OPENROUTER_API_KEY / OPENROUTER_MODEL
# и старые PROVIDER_API_KEY / PROVIDER_MODEL для обратной совместимости.
LLM_BASE_URL: str = os.getenv("PROVIDER_BASE_URL", "https://openrouter.ai/api/v1")
LLM_API_KEY: str = os.getenv(
    "OPENROUTER_API_KEY",
    os.getenv("PROVIDER_API_KEY", os.getenv("SCORE_LLM_API_KEY", "")),
)
LLM_MODEL: str = os.getenv(
    "OPENROUTER_MODEL",
    os.getenv("PROVIDER_MODEL", os.getenv("SCORE_LLM_MODEL", "anthropic/claude-sonnet-4")),
)

# Metadata cache
METADATA_CACHE_FILE: str = os.getenv("METADATA_CACHE_FILE", "metadata_cache.json")
METADATA_CACHE_TTL_HOURS: int = int(
    os.getenv("METADATA_CACHE_HOURS", os.getenv("METADATA_CACHE_TTL_HOURS", "24"))
)

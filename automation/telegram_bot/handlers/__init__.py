# -*- coding: utf-8 -*-
"""
Пакет обработчиков команд Telegram-бота.
"""

from .start import router as start_router
from .analytics import router as analytics_router
from .inventory import router as inventory_router
from .finance import router as finance_router
from .free_question import router as free_question_router

__all__ = [
    "start_router",
    "analytics_router",
    "inventory_router",
    "finance_router",
    "free_question_router",
]

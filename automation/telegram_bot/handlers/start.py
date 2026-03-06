# -*- coding: utf-8 -*-
"""
Обработчики команды /start и главного меню.
"""

import logging

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import metadata_scanner
import onec_connector
import config

logger = logging.getLogger(__name__)
router = Router()


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика продаж", callback_data="menu:analytics")],
        [InlineKeyboardButton(text="📦 Склад и остатки", callback_data="menu:inventory")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance")],
        [InlineKeyboardButton(text="💬 Свободный вопрос", callback_data="menu:free_question")],
    ])


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user_id = message.from_user.id
    if user_id not in config.TELEGRAM_ALLOWED_USERS:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        logger.warning("Попытка доступа от неизвестного пользователя: %d", user_id)
        return

    # Запускаем сканирование метаданных в фоне (не блокирует ответ)
    await message.answer("⏳ Подключаюсь к базе 1С...")
    try:
        com_obj = onec_connector.connect(
            config.ONEC_CONNECTION_STRING,
            config.ONEC_USER,
            config.ONEC_PASSWORD,
        )
        cache = metadata_scanner.get_or_scan(com_obj)
        caps_text = _capabilities_text(cache)
    except Exception as exc:
        logger.error("Ошибка подключения к 1С при /start: %s", exc)
        caps_text = "⚠️ Не удалось подключиться к базе 1С."

    await message.answer(
        f"👋 *Добро пожаловать!*\n\n"
        f"🤖 AI Бизнес-Ассистент для 1С\n\n"
        f"{caps_text}\n\n"
        f"Выберите раздел:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )


@router.callback_query(lambda c: c.data == "menu:main")
async def menu_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📋 *Главное меню*\n\nВыберите раздел:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )
    await callback.answer()


def _capabilities_text(cache: metadata_scanner.MetadataCache) -> str:
    lines = []
    if cache.capabilities.get("sales"):
        lines.append("✅ Аналитика продаж")
    if cache.capabilities.get("inventory"):
        lines.append("✅ Склад и остатки")
    if cache.capabilities.get("finance"):
        lines.append("✅ Финансы")
    if not lines:
        lines.append("ℹ️ Возможности базы определятся после сканирования")
    return "Доступные разделы:\n" + "\n".join(lines)

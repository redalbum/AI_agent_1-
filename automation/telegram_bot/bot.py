# -*- coding: utf-8 -*-
"""
Главный файл Telegram-бота бизнес-ассистента 1С.

Запуск:
    python -m automation.telegram_bot.bot
    # или из каталога automation/telegram_bot:
    python bot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

# Настройка путей для импорта com_1c
_bot_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_bot_dir)
if _automation_dir not in sys.path:
    sys.path.insert(0, _automation_dir)

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from .config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_ALLOWED_USERS,
    ONEC_CONNECTION_STRING,
    ONEC_USER,
    ONEC_PASSWORD,
    LLM_BASE_URL,
    LLM_API_KEY,
    LLM_MODEL,
    METADATA_CACHE_FILE,
    METADATA_CACHE_TTL_HOURS,
)
from .onec_connector import OneCConnector
from .llm_client import LLMClient
from .metadata_scanner import MetadataScanner
from .handlers import (
    analytics_router,
    inventory_router,
    finance_router,
    free_question_router,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ---------- Глобальные синглтоны ----------

_connector: Optional[OneCConnector] = None
_llm_client: Optional[LLMClient] = None
_metadata_cache: Optional[dict] = None


def get_connector() -> Optional[OneCConnector]:
    return _connector


def get_llm_client() -> Optional[LLMClient]:
    return _llm_client


def get_metadata_cache() -> Optional[dict]:
    return _metadata_cache


# ---------- Клавиатуры ----------

def _main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📊 Аналитика продаж", callback_data="menu:analytics"),
            InlineKeyboardButton(text="📦 Склад и закупки", callback_data="menu:inventory"),
        ],
        [
            InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance"),
            InlineKeyboardButton(text="💬 Свободный вопрос", callback_data="menu:free_question"),
        ],
        [InlineKeyboardButton(text="⚙️ Настройки", callback_data="menu:settings")],
    ])


def _settings_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Пересканировать метаданные 1С", callback_data="settings:rescan")],
        [InlineKeyboardButton(text="🔌 Проверить подключение", callback_data="settings:test_connection")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def _scan_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да, сканировать", callback_data="scan:confirm"),
            InlineKeyboardButton(text="❌ Пропустить", callback_data="scan:skip"),
        ],
    ])


# ---------- Вспомогательные функции ----------

def _is_allowed(user_id: int) -> bool:
    """Проверяет, разрешён ли доступ пользователю."""
    if not TELEGRAM_ALLOWED_USERS:
        return True  # Если список пуст — доступ для всех
    return user_id in TELEGRAM_ALLOWED_USERS


async def _ensure_connection() -> bool:
    """Устанавливает COM-подключение если ещё не установлено."""
    global _connector
    if _connector is not None and _connector.is_connected:
        return True
    if not ONEC_CONNECTION_STRING:
        logger.warning("ONEC_BASE_PATH (или ONEC_CONNECTION_STRING) не задан.")
        return False
    _connector = OneCConnector(ONEC_CONNECTION_STRING, ONEC_USER, ONEC_PASSWORD)
    result = await _connector.connect()
    if result:
        logger.info("Подключение к 1С установлено.")
    else:
        logger.error("Не удалось подключиться к 1С.")
        _connector = None
    return result


async def _load_or_scan_metadata(force: bool = False) -> Optional[dict]:
    """Загружает кеш метаданных или запускает сканирование."""
    global _metadata_cache, _connector
    scanner = MetadataScanner(_connector, _llm_client)

    if not force:
        cached = scanner.load_cache(METADATA_CACHE_FILE)
        if cached and scanner.is_cache_valid(cached, METADATA_CACHE_TTL_HOURS):
            logger.info("Метаданные загружены из кеша.")
            return cached

    if _connector is None or not _connector.is_connected:
        logger.warning("Нет подключения к 1С — сканирование невозможно.")
        return None

    logger.info("Сканирование метаданных…")
    metadata = await scanner.scan_metadata()
    scanner.save_cache(METADATA_CACHE_FILE, metadata)
    return metadata


# ---------- Обработчики ----------

dp = Dispatcher(storage=MemoryStorage())

# Подключаем роутеры обработчиков
dp.include_router(analytics_router)
dp.include_router(inventory_router)
dp.include_router(finance_router)
dp.include_router(free_question_router)


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        await message.answer("⛔️ Доступ запрещён.")
        return

    global _metadata_cache
    connected = await _ensure_connection()

    if not connected:
        # Нет подключения, но всё равно показываем приветствие
        await message.answer(
            "🤖 <b>Бизнес-ассистент 1С</b>\n\n"
            "⚠️ Не удалось подключиться к базе 1С.\n"
            "Проверьте настройку <code>ONEC_BASE_PATH</code> в файле .env.\n\n"
            "Вы можете попробовать позже или использовать доступные функции.",
            reply_markup=_main_menu_kb(),
            parse_mode="HTML",
        )
        return

    # Загружаем кеш метаданных
    cached = MetadataScanner(_connector).load_cache(METADATA_CACHE_FILE)
    scanner = MetadataScanner(_connector)
    if cached and scanner.is_cache_valid(cached, METADATA_CACHE_TTL_HOURS):
        _metadata_cache = cached
        await message.answer(
            "🤖 <b>Бизнес-ассистент 1С</b>\n\n"
            "✅ Подключён к базе 1С.\n"
            "Метаданные загружены из кеша.\n\n"
            "Выберите раздел:",
            reply_markup=_main_menu_kb(),
            parse_mode="HTML",
        )
    else:
        # Предлагаем сканировать
        await message.answer(
            "🤖 <b>Бизнес-ассистент 1С</b>\n\n"
            "✅ Подключён к базе 1С.\n\n"
            "🔍 Кеш метаданных отсутствует или устарел.\n"
            "Отсканировать структуру базы? (занимает ~30 секунд)",
            reply_markup=_scan_confirm_kb(),
            parse_mode="HTML",
        )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "🤖 <b>Бизнес-ассистент 1С — Помощь</b>\n\n"
        "<b>Команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/scan — пересканировать метаданные 1С\n"
        "/status — статус подключения\n\n"
        "<b>Разделы:</b>\n"
        "📊 <b>Аналитика</b> — топ продаж, аутсайдеры, динамика\n"
        "📦 <b>Склад</b> — остатки, дефицит, залежалые\n"
        "💰 <b>Финансы</b> — дебиторка, кредиторка, касса\n"
        "💬 <b>Свободный вопрос</b> — любой вопрос к базе\n",
        parse_mode="HTML",
    )


@dp.message(Command("scan"))
async def cmd_scan(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    await message.answer(
        "🔍 Запустить полное сканирование метаданных базы 1С?",
        reply_markup=_scan_confirm_kb(),
    )


@dp.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not _is_allowed(message.from_user.id):
        return
    connected = _connector is not None and _connector.is_connected
    has_cache = _metadata_cache is not None
    llm_ok = _llm_client is not None and bool(LLM_API_KEY)
    lines = [
        "⚙️ <b>Статус подключений</b>\n",
        f"1С: {'✅ подключено' if connected else '❌ нет подключения'}",
        f"LLM: {'✅ настроен' if llm_ok else '⚠️ API-ключ не задан'}",
        f"Метаданные: {'✅ загружены' if has_cache else '⚠️ не загружены'}",
        f"\nМодель: <code>{LLM_MODEL}</code>",
        f"Кеш: <code>{METADATA_CACHE_FILE}</code>",
    ]
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.callback_query(F.data == "menu:main")
async def menu_main(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🤖 <b>Бизнес-ассистент 1С</b>\n\nВыберите раздел:",
        reply_markup=_main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "menu:settings")
async def menu_settings(callback: CallbackQuery) -> None:
    connected = _connector is not None and _connector.is_connected
    has_cache = _metadata_cache is not None
    text = (
        "⚙️ <b>Настройки</b>\n\n"
        f"1С: {'✅ подключено' if connected else '❌ нет подключения'}\n"
        f"Метаданные: {'✅ загружены' if has_cache else '⚠️ не загружены'}\n"
        f"LLM: <code>{LLM_MODEL}</code>"
    )
    await callback.message.edit_text(text, reply_markup=_settings_kb(), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "settings:test_connection")
async def settings_test_connection(callback: CallbackQuery) -> None:
    await callback.message.edit_text("⏳ Проверяю подключение к 1С…")
    await callback.answer()
    result = await _ensure_connection()
    text = (
        "✅ Подключение к 1С успешно установлено."
        if result
        else "❌ Не удалось подключиться к 1С.\nПроверьте строку подключения в .env"
    )
    await callback.message.edit_text(text, reply_markup=_settings_kb())


@dp.callback_query(F.data == "settings:rescan")
async def settings_rescan(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🔍 Запустить полное пересканирование метаданных?",
        reply_markup=_scan_confirm_kb(),
    )
    await callback.answer()


@dp.callback_query(F.data == "scan:confirm")
async def scan_confirm(callback: CallbackQuery) -> None:
    global _metadata_cache
    await callback.message.edit_text("⏳ Сканирую метаданные 1С…\nЭто займёт ~30 секунд.")
    await callback.answer()

    if not await _ensure_connection():
        await callback.message.edit_text(
            "❌ Не удалось подключиться к 1С. Проверьте настройки.",
            reply_markup=_main_menu_kb(),
        )
        return

    try:
        _metadata_cache = await _load_or_scan_metadata(force=True)
        if _metadata_cache:
            total = sum(
                len(v) for v in _metadata_cache.get("objects_list", {}).values()
            )
            await callback.message.edit_text(
                f"✅ Сканирование завершено!\n"
                f"Обнаружено объектов: <b>{total}</b>\n\n"
                "Выберите раздел:",
                reply_markup=_main_menu_kb(),
                parse_mode="HTML",
            )
        else:
            await callback.message.edit_text(
                "⚠️ Сканирование завершено, но метаданные не получены.\n"
                "Проверьте права доступа к базе 1С.",
                reply_markup=_main_menu_kb(),
            )
    except Exception as exc:
        logger.error("Ошибка сканирования: %s", exc)
        await callback.message.edit_text(
            f"❌ Ошибка сканирования:\n<code>{exc}</code>",
            reply_markup=_main_menu_kb(),
            parse_mode="HTML",
        )


@dp.callback_query(F.data == "scan:skip")
async def scan_skip(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "🤖 <b>Бизнес-ассистент 1С</b>\n\nВыберите раздел:",
        reply_markup=_main_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


# ---------- Запуск ----------

async def main() -> None:
    global _llm_client, _metadata_cache

    if not TELEGRAM_BOT_TOKEN:
        logger.critical(
            "TELEGRAM_BOT_TOKEN не задан. Добавьте его в .env и перезапустите."
        )
        sys.exit(1)

    # Инициализируем LLM-клиент
    if LLM_API_KEY:
        _llm_client = LLMClient(LLM_BASE_URL, LLM_API_KEY, LLM_MODEL)
        logger.info("LLM-клиент инициализирован: %s", LLM_MODEL)
    else:
        logger.warning("OPENROUTER_API_KEY не задан — LLM-функции недоступны.")

    # Подключаемся к 1С
    connected = await _ensure_connection()

    # Загружаем кеш метаданных при старте
    if connected:
        _metadata_cache = await _load_or_scan_metadata(force=False)

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    logger.info("Бот запущен.")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        if _connector:
            await _connector.disconnect()
        if _llm_client:
            await _llm_client.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

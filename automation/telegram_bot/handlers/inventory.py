# -*- coding: utf-8 -*-
"""
Обработчики раздела "Склад и остатки".
"""

import logging
from datetime import date, timedelta

from aiogram import Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

import config
import llm_client
import onec_connector
import prompts

logger = logging.getLogger(__name__)
router = Router()

_BACK = InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")


def _inventory_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Текущие остатки", callback_data="inventory:current")],
        [InlineKeyboardButton(text="⚠️ Дефицит (остаток < 5)", callback_data="inventory:deficit")],
        [InlineKeyboardButton(text="📦 Залежавшийся товар (90+ дней)", callback_data="inventory:stale")],
        [InlineKeyboardButton(text="🛒 Рекомендации по закупкам", callback_data="inventory:reorder")],
        [_BACK],
    ])


@router.callback_query(lambda c: c.data == "menu:inventory")
async def inventory_menu(callback: CallbackQuery) -> None:
    if callback.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "📦 *Склад и остатки*\n\nВыберите отчёт:",
        parse_mode="Markdown",
        reply_markup=_inventory_menu(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("inventory:"))
async def inventory_action(callback: CallbackQuery) -> None:
    if callback.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    action = callback.data.split(":", 1)[1]
    await callback.answer()
    await callback.message.edit_text("⏳ Получаю данные из 1С...")

    com_obj = onec_connector.connect(
        config.ONEC_CONNECTION_STRING, config.ONEC_USER, config.ONEC_PASSWORD
    )
    if com_obj is None:
        await callback.message.edit_text(
            "❌ Не удалось подключиться к базе 1С.\n"
            "Проверьте ONEC_CONNECTION_STRING в настройках.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    today = date.today()

    if action == "current":
        query = _current_stock_query()
        cols = ["Номенклатура", "Остаток"]
        question = "Текущие остатки товаров на складе"
    elif action == "deficit":
        query = _deficit_query()
        cols = ["Номенклатура", "Остаток"]
        question = "Товары с критически низким остатком (менее 5 единиц)"
    elif action == "stale":
        stale_date = today - timedelta(days=90)
        query = _stale_query(stale_date)
        cols = ["Номенклатура", "Остаток", "ПоследняяПродажа"]
        question = "Товары, которые не продавались более 90 дней"
    elif action == "reorder":
        query = _reorder_query()
        cols = ["Номенклатура", "Остаток", "СреднедневноеПотребление"]
        question = "Рекомендации по закупкам на основе остатков и потребления"
    else:
        await callback.message.edit_text(
            "❌ Неизвестный отчёт",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    rows = onec_connector.execute_query(com_obj, query, cols)
    data_text = _format_table(rows, cols) if rows else "Нет данных."
    await callback.message.edit_text("⏳ Анализирую данные...")

    answer = await llm_client.ask(
        prompts.analytics_prompt(data_text, question),
        system_message=prompts.SYSTEM_ANALYST,
    )
    await callback.message.edit_text(
        f"📦 *{question}*\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
    )


# --- Запросы 1С ---

def _current_stock_query() -> str:
    return (
        "ВЫБРАТЬ\n"
        "    ТоварыНаСкладахОстатки.Номенклатура КАК Номенклатура,\n"
        "    ТоварыНаСкладахОстатки.КоличествоОстаток КАК Остаток\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК ТоварыНаСкладахОстатки\n"
        "ГДЕ\n"
        "    ТоварыНаСкладахОстатки.КоличествоОстаток > 0\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Остаток УБЫВ\n"
        "ПЕРВЫЕ 30"
    )


def _deficit_query() -> str:
    return (
        "ВЫБРАТЬ\n"
        "    ТоварыНаСкладахОстатки.Номенклатура КАК Номенклатура,\n"
        "    ТоварыНаСкладахОстатки.КоличествоОстаток КАК Остаток\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК ТоварыНаСкладахОстатки\n"
        "ГДЕ\n"
        "    ТоварыНаСкладахОстатки.КоличествоОстаток < 5\n"
        "    И ТоварыНаСкладахОстатки.КоличествоОстаток >= 0\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Остаток"
    )


def _stale_query(stale_date: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    Остатки.Номенклатура КАК Номенклатура,\n"
        "    Остатки.КоличествоОстаток КАК Остаток,\n"
        "    МАКСИМУМ(Продажи.Период) КАК ПоследняяПродажа\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК Остатки\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.Продажи КАК Продажи\n"
        "        ПО Остатки.Номенклатура = Продажи.Номенклатура\n"
        "ГДЕ\n"
        "    Остатки.КоличествоОстаток > 0\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    Остатки.Номенклатура, Остатки.КоличествоОстаток\n"
        "ИМЕЮЩИЕ\n"
        f"    (МАКСИМУМ(Продажи.Период) < ДАТАВРЕМЯ({stale_date.year},{stale_date.month},{stale_date.day})\n"
        "    ИЛИ МАКСИМУМ(Продажи.Период) ЕСТЬ NULL)\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    ПоследняяПродажа"
    )


def _reorder_query() -> str:
    return (
        "ВЫБРАТЬ\n"
        "    Остатки.Номенклатура КАК Номенклатура,\n"
        "    Остатки.КоличествоОстаток КАК Остаток,\n"
        "    ЕСТЬNULL(СУММА(Продажи.Количество) / 30, 0) КАК СреднедневноеПотребление\n"
        "ИЗ\n"
        "    РегистрНакопления.ТоварыНаСкладах.Остатки() КАК Остатки\n"
        "        ЛЕВОЕ СОЕДИНЕНИЕ РегистрНакопления.Продажи КАК Продажи\n"
        "        ПО Остатки.Номенклатура = Продажи.Номенклатура\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    Остатки.Номенклатура, Остатки.КоличествоОстаток\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Остаток\n"
        "ПЕРВЫЕ 20"
    )


def _format_table(rows: list[dict], cols: list[str]) -> str:
    lines = [" | ".join(cols)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    return "\n".join(lines)

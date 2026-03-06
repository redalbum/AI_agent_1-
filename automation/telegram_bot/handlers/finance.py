# -*- coding: utf-8 -*-
"""
Обработчики раздела "Финансы".
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


def _finance_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Выручка за сегодня", callback_data="finance:today")],
        [InlineKeyboardButton(text="📅 Выручка за неделю", callback_data="finance:week")],
        [InlineKeyboardButton(text="🗓️ Выручка за месяц", callback_data="finance:month")],
        [InlineKeyboardButton(text="🧾 Средний чек (месяц)", callback_data="finance:avg_check")],
        [_BACK],
    ])


@router.callback_query(lambda c: c.data == "menu:finance")
async def finance_menu(callback: CallbackQuery) -> None:
    if callback.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "💰 *Финансы*\n\nВыберите отчёт:",
        parse_mode="Markdown",
        reply_markup=_finance_menu(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("finance:"))
async def finance_action(callback: CallbackQuery) -> None:
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

    if action == "today":
        period_start = today
        question = "Финансовые показатели за сегодня"
    elif action == "week":
        period_start = today - timedelta(days=7)
        question = "Финансовые показатели за последние 7 дней"
    elif action == "month":
        period_start = today.replace(day=1)
        question = "Финансовые показатели за текущий месяц"
    elif action == "avg_check":
        period_start = today.replace(day=1)
        query = _avg_check_query(period_start, today)
        cols = ["КоличествоЧеков", "СреднийЧек", "ОбщаяВыручка"]
        rows = onec_connector.execute_query(com_obj, query, cols)
        data_text = _format_table(rows, cols) if rows else "Нет данных."
        await callback.message.edit_text("⏳ Анализирую данные...")
        answer = await llm_client.ask(
            prompts.analytics_prompt(data_text, "Средний чек и количество чеков за текущий месяц"),
            system_message=prompts.SYSTEM_ANALYST,
        )
        await callback.message.edit_text(
            f"💰 *Средний чек за текущий месяц*\n\n{answer}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return
    else:
        await callback.message.edit_text(
            "❌ Неизвестный отчёт",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    query = _revenue_query(period_start, today)
    cols = ["Дата", "Выручка"]
    rows = onec_connector.execute_query(com_obj, query, cols)
    data_text = _format_table(rows, cols) if rows else "Нет данных за период."
    await callback.message.edit_text("⏳ Анализирую данные...")

    answer = await llm_client.ask(
        prompts.analytics_prompt(data_text, question),
        system_message=prompts.SYSTEM_ANALYST,
    )
    await callback.message.edit_text(
        f"💰 *{question}*\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
    )


# --- Запросы 1С ---

def _revenue_query(period_start: date, period_end: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    НАЧАЛОПЕРИОДА(Продажи.Период, ДЕНЬ) КАК Дата,\n"
        "    СУММА(Продажи.Сумма) КАК Выручка\n"
        "ИЗ\n"
        "    РегистрНакопления.Продажи КАК Продажи\n"
        f"ГДЕ\n"
        f"    Продажи.Период МЕЖДУ ДАТАВРЕМЯ({period_start.year},{period_start.month},{period_start.day})"
        f" И ДАТАВРЕМЯ({period_end.year},{period_end.month},{period_end.day})\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    НАЧАЛОПЕРИОДА(Продажи.Период, ДЕНЬ)\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Дата"
    )


def _avg_check_query(period_start: date, period_end: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    КОЛИЧЕСТВО(РАЗЛИЧНЫЕ Продажи.Регистратор) КАК КоличествоЧеков,\n"
        "    СУММА(Продажи.Сумма) / КОЛИЧЕСТВО(РАЗЛИЧНЫЕ Продажи.Регистратор) КАК СреднийЧек,\n"
        "    СУММА(Продажи.Сумма) КАК ОбщаяВыручка\n"
        "ИЗ\n"
        "    РегистрНакопления.Продажи КАК Продажи\n"
        f"ГДЕ\n"
        f"    Продажи.Период МЕЖДУ ДАТАВРЕМЯ({period_start.year},{period_start.month},{period_start.day})"
        f" И ДАТАВРЕМЯ({period_end.year},{period_end.month},{period_end.day})"
    )


def _format_table(rows: list[dict], cols: list[str]) -> str:
    lines = [" | ".join(cols)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    return "\n".join(lines)

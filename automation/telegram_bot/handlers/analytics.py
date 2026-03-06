# -*- coding: utf-8 -*-
"""
Обработчики раздела "Аналитика продаж".
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


def _analytics_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏆 Топ продаж (неделя)", callback_data="analytics:top_week")],
        [InlineKeyboardButton(text="🏆 Топ продаж (месяц)", callback_data="analytics:top_month")],
        [InlineKeyboardButton(text="📉 Аутсайдеры (месяц)", callback_data="analytics:worst_month")],
        [InlineKeyboardButton(text="📈 Динамика (мес. к мес.)", callback_data="analytics:dynamics")],
        [_BACK],
    ])


@router.callback_query(lambda c: c.data == "menu:analytics")
async def analytics_menu(callback: CallbackQuery) -> None:
    if callback.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return
    await callback.message.edit_text(
        "📊 *Аналитика продаж*\n\nВыберите отчёт:",
        parse_mode="Markdown",
        reply_markup=_analytics_menu(),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data and c.data.startswith("analytics:"))
async def analytics_action(callback: CallbackQuery) -> None:
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

    if action == "top_week":
        period_start = today - timedelta(days=7)
        query, cols, question = _top_sales_query(period_start, today), \
            ["Номенклатура", "Количество", "Сумма"], \
            "Топ-10 продаж за последние 7 дней"
    elif action == "top_month":
        period_start = today.replace(day=1)
        query, cols, question = _top_sales_query(period_start, today), \
            ["Номенклатура", "Количество", "Сумма"], \
            "Топ-10 продаж за текущий месяц"
    elif action == "worst_month":
        period_start = today.replace(day=1)
        query, cols, question = _worst_sales_query(period_start, today), \
            ["Номенклатура", "Количество", "Сумма"], \
            "Товары-аутсайдеры за текущий месяц (наименьшие продажи)"
    elif action == "dynamics":
        this_month_start = today.replace(day=1)
        prev_month_end = this_month_start - timedelta(days=1)
        prev_month_start = prev_month_end.replace(day=1)
        query, cols, question = _dynamics_query(prev_month_start, today), \
            ["Месяц", "Сумма"], \
            "Динамика продаж: сравнение текущего и предыдущего месяца"
    else:
        await callback.message.edit_text(
            "❌ Неизвестный отчёт",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    rows = onec_connector.execute_query(com_obj, query, cols)
    data_text = _format_table(rows, cols) if rows else "Нет данных за период."
    await callback.message.edit_text("⏳ Анализирую данные...")

    answer = await llm_client.ask(
        prompts.analytics_prompt(data_text, question),
        system_message=prompts.SYSTEM_ANALYST,
    )
    await callback.message.edit_text(
        f"📊 *{question}*\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
    )


# --- Запросы 1С ---

def _top_sales_query(period_start: date, period_end: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    Продажи.Номенклатура КАК Номенклатура,\n"
        "    СУММА(Продажи.Количество) КАК Количество,\n"
        "    СУММА(Продажи.Сумма) КАК Сумма\n"
        "ИЗ\n"
        "    РегистрНакопления.Продажи КАК Продажи\n"
        f"ГДЕ\n"
        f"    Продажи.Период МЕЖДУ ДАТАВРЕМЯ({period_start.year},{period_start.month},{period_start.day})"
        f" И ДАТАВРЕМЯ({period_end.year},{period_end.month},{period_end.day})\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    Продажи.Номенклатура\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Сумма УБЫВ\n"
        "ПЕРВЫЕ 10"
    )


def _worst_sales_query(period_start: date, period_end: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    Продажи.Номенклатура КАК Номенклатура,\n"
        "    СУММА(Продажи.Количество) КАК Количество,\n"
        "    СУММА(Продажи.Сумма) КАК Сумма\n"
        "ИЗ\n"
        "    РегистрНакопления.Продажи КАК Продажи\n"
        f"ГДЕ\n"
        f"    Продажи.Период МЕЖДУ ДАТАВРЕМЯ({period_start.year},{period_start.month},{period_start.day})"
        f" И ДАТАВРЕМЯ({period_end.year},{period_end.month},{period_end.day})\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    Продажи.Номенклатура\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Сумма\n"
        "ПЕРВЫЕ 10"
    )


def _dynamics_query(period_start: date, period_end: date) -> str:
    return (
        "ВЫБРАТЬ\n"
        "    НАЧАЛОПЕРИОДА(Продажи.Период, МЕСЯЦ) КАК Месяц,\n"
        "    СУММА(Продажи.Сумма) КАК Сумма\n"
        "ИЗ\n"
        "    РегистрНакопления.Продажи КАК Продажи\n"
        f"ГДЕ\n"
        f"    Продажи.Период МЕЖДУ ДАТАВРЕМЯ({period_start.year},{period_start.month},{period_start.day})"
        f" И ДАТАВРЕМЯ({period_end.year},{period_end.month},{period_end.day})\n"
        "СГРУППИРОВАТЬ ПО\n"
        "    НАЧАЛОПЕРИОДА(Продажи.Период, МЕСЯЦ)\n"
        "УПОРЯДОЧИТЬ ПО\n"
        "    Месяц"
    )


def _format_table(rows: list[dict], cols: list[str]) -> str:
    lines = [" | ".join(cols)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    return "\n".join(lines)

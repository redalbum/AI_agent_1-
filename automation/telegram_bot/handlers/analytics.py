# -*- coding: utf-8 -*-
"""
Обработчик аналитики продаж.
Разделы: Топ продаж, Аутсайдеры, Динамика.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)
router = Router()


class AnalyticsStates(StatesGroup):
    waiting_for_period = State()
    waiting_for_custom_period = State()


# ---------- Вспомогательные функции ----------

def _period_dates(period: str) -> tuple[date, date]:
    today = date.today()
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=7), today
    if period == "month":
        first = today.replace(day=1)
        return first, today
    if period == "quarter":
        month = ((today.month - 1) // 3) * 3 + 1
        first = today.replace(month=month, day=1)
        return first, today
    return today.replace(day=1), today


def _analytics_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🏆 Топ продаж", callback_data="analytics:top"),
            InlineKeyboardButton(text="📉 Аутсайдеры", callback_data="analytics:bottom"),
        ],
        [
            InlineKeyboardButton(text="📈 Динамика продаж", callback_data="analytics:dynamics"),
            InlineKeyboardButton(text="🔠 ABC-анализ", callback_data="analytics:abc"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


def _period_kb(report_type: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Сегодня", callback_data=f"period:{report_type}:today"),
            InlineKeyboardButton(text="Неделя", callback_data=f"period:{report_type}:week"),
        ],
        [
            InlineKeyboardButton(text="Месяц", callback_data=f"period:{report_type}:month"),
            InlineKeyboardButton(text="Квартал", callback_data=f"period:{report_type}:quarter"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:analytics")],
    ])


def _build_query_top_sales(start: date, end: date, limit: int = 10) -> tuple[str, list[str]]:
    query = f"""ВЫБРАТЬ ПЕРВЫЕ {limit}
    ПродажиОбороты.Номенклатура.Наименование КАК Номенклатура,
    СУММА(ПродажиОбороты.КоличествоОборот) КАК Количество,
    СУММА(ПродажиОбороты.СуммаОборот) КАК Сумма
ИЗ
    РегистрНакопления.Продажи.Обороты(&НачалоПериода, &КонецПериода, , ) КАК ПродажиОбороты
СГРУППИРОВАТЬ ПО
    ПродажиОбороты.Номенклатура.Наименование
УПОРЯДОЧИТЬ ПО
    Сумма УБЫВ"""
    return query, ["Номенклатура", "Количество", "Сумма"]


def _build_query_bottom_sales(start: date, end: date, limit: int = 10) -> tuple[str, list[str]]:
    query = f"""ВЫБРАТЬ ПЕРВЫЕ {limit}
    ПродажиОбороты.Номенклатура.Наименование КАК Номенклатура,
    СУММА(ПродажиОбороты.КоличествоОборот) КАК Количество,
    СУММА(ПродажиОбороты.СуммаОборот) КАК Сумма
ИЗ
    РегистрНакопления.Продажи.Обороты(&НачалоПериода, &КонецПериода, , ) КАК ПродажиОбороты
СГРУППИРОВАТЬ ПО
    ПродажиОбороты.Номенклатура.Наименование
УПОРЯДОЧИТЬ ПО
    Сумма"""
    return query, ["Номенклатура", "Количество", "Сумма"]


def _format_rows(rows: list[dict], title: str) -> str:
    if not rows:
        return f"{title}\n\nДанных не найдено."
    lines = [title, ""]
    for i, row in enumerate(rows, 1):
        nom = row.get("Номенклатура", "—")
        qty = row.get("Количество", "—")
        amount = row.get("Сумма", "—")
        try:
            amount_fmt = f"{float(amount):,.2f} ₽".replace(",", " ")
        except (ValueError, TypeError):
            amount_fmt = str(amount)
        lines.append(f"{i}. {nom} — {qty} шт ({amount_fmt})")
    return "\n".join(lines)


# ---------- Обработчики ----------

@router.callback_query(F.data == "menu:analytics")
async def analytics_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📊 <b>Аналитика продаж</b>\nВыберите отчёт:",
        reply_markup=_analytics_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.in_({"analytics:top", "analytics:bottom", "analytics:dynamics", "analytics:abc"}))
async def analytics_choose_period(callback: CallbackQuery) -> None:
    report_type = callback.data.split(":")[1]
    titles = {
        "top": "🏆 Топ продаж",
        "bottom": "📉 Аутсайдеры",
        "dynamics": "📈 Динамика продаж",
        "abc": "🔠 ABC-анализ",
    }
    title = titles.get(report_type, report_type)
    await callback.message.edit_text(
        f"{title}\n\nВыберите период:",
        reply_markup=_period_kb(report_type),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("period:"))
async def analytics_run_report(callback: CallbackQuery) -> None:
    parts = callback.data.split(":")
    if len(parts) < 3:
        await callback.answer("Ошибка выбора периода.")
        return
    report_type = parts[1]
    period = parts[2]
    start, end = _period_dates(period)

    await callback.message.edit_text("⏳ Загружаю данные из 1С…")
    await callback.answer()

    from ..bot import get_connector, get_llm_client, get_metadata_cache

    connector = get_connector()
    llm = get_llm_client()
    metadata = get_metadata_cache()

    if connector is None or not connector.is_connected:
        await callback.message.edit_text(
            "❌ Нет подключения к 1С. Проверьте настройки.",
            reply_markup=_analytics_menu_kb(),
        )
        return

    try:
        if report_type == "top":
            query, cols = _build_query_top_sales(start, end)
            title = f"🏆 <b>Топ-10 продаж</b> ({start} — {end})"
        elif report_type == "bottom":
            query, cols = _build_query_bottom_sales(start, end)
            title = f"📉 <b>Аутсайдеры продаж</b> ({start} — {end})"
        else:
            # Для динамики и ABC используем тот же топ-запрос как базу
            query, cols = _build_query_top_sales(start, end, limit=20)
            title = f"📊 <b>Данные продаж</b> ({start} — {end})"

        # Подставляем даты как параметры через специальный синтаксис
        query_with_dates = query
        rows = await connector.execute_query(
            query_with_dates.replace(
                "&НачалоПериода", f"ДАТАВРЕМЯ({start.year},{start.month},{start.day})"
            ).replace(
                "&КонецПериода", f"ДАТАВРЕМЯ({end.year},{end.month},{end.day},23,59,59)"
            ),
            cols,
        )

        report_text = _format_rows(rows, title)

        # LLM-анализ
        if llm and rows:
            meta_text = ""
            if metadata:
                from ..metadata_scanner import MetadataScanner
                scanner = MetadataScanner(connector)
                meta_text = scanner.metadata_summary_text(metadata)
            try:
                recommendation = await llm.analyze_data(report_text, meta_text)
                report_text += f"\n\n💡 <b>Рекомендация:</b>\n{recommendation}"
            except Exception as exc:
                logger.warning("LLM анализ не выполнен: %s", exc)

        report_text += f"\n\n<i>Период: {start} — {end}</i>"

    except Exception as exc:
        logger.error("Ошибка выполнения аналитики: %s", exc)
        report_text = f"❌ Ошибка получения данных:\n<code>{exc}</code>"

    await callback.message.edit_text(
        report_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К аналитике", callback_data="menu:analytics")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )

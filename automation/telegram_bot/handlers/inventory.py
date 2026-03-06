# -*- coding: utf-8 -*-
"""
Обработчик раздела «Склад и закупки».
Разделы: остатки товаров, дефицит, залежалые позиции.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()


def _inventory_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Остатки товаров", callback_data="inventory:remains"),
            InlineKeyboardButton(text="⚠️ Дефицит", callback_data="inventory:deficit"),
        ],
        [
            InlineKeyboardButton(text="🕰 Залежалые позиции", callback_data="inventory:slow_moving"),
            InlineKeyboardButton(text="📦 Заказы поставщикам", callback_data="inventory:orders"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


@router.callback_query(F.data == "menu:inventory")
async def inventory_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "📦 <b>Склад и закупки</b>\nВыберите отчёт:",
        reply_markup=_inventory_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("inventory:"))
async def inventory_report(callback: CallbackQuery) -> None:
    report_type = callback.data.split(":")[1]

    queries: dict[str, tuple[str, list[str]]] = {
        "remains": (
            """ВЫБРАТЬ ПЕРВЫЕ 50
    ТоварыНаСкладахОстатки.Номенклатура.Наименование КАК Номенклатура,
    ТоварыНаСкладахОстатки.КоличествоОстаток КАК Остаток
ИЗ
    РегистрНакопления.ТоварыНаСкладах.Остатки AS ТоварыНаСкладахОстатки
ГДЕ
    ТоварыНаСкладахОстатки.КоличествоОстаток > 0
УПОРЯДОЧИТЬ ПО
    Остаток УБЫВ""",
            ["Номенклатура", "Остаток"],
        ),
        "deficit": (
            """ВЫБРАТЬ ПЕРВЫЕ 30
    ТоварыНаСкладахОстатки.Номенклатура.Наименование КАК Номенклатура,
    ТоварыНаСкладахОстатки.КоличествоОстаток КАК Остаток
ИЗ
    РегистрНакопления.ТоварыНаСкладах.Остатки AS ТоварыНаСкладахОстатки
ГДЕ
    ТоварыНаСкладахОстатки.КоличествоОстаток <= 0
УПОРЯДОЧИТЬ ПО
    Остаток""",
            ["Номенклатура", "Остаток"],
        ),
        "slow_moving": (
            """ВЫБРАТЬ ПЕРВЫЕ 30
    ТоварыНаСкладахОстатки.Номенклатура.Наименование КАК Номенклатура,
    ТоварыНаСкладахОстатки.КоличествоОстаток КАК Остаток
ИЗ
    РегистрНакопления.ТоварыНаСкладах.Остатки AS ТоварыНаСкладахОстатки
ГДЕ
    ТоварыНаСкладахОстатки.КоличествоОстаток > 100
УПОРЯДОЧИТЬ ПО
    Остаток УБЫВ""",
            ["Номенклатура", "Остаток"],
        ),
        "orders": (
            """ВЫБРАТЬ ПЕРВЫЕ 30
    ЗаказПоставщику.Номер КАК Номер,
    ЗаказПоставщику.Дата КАК Дата,
    ЗаказПоставщику.Контрагент.Наименование КАК Поставщик,
    ЗаказПоставщику.СуммаДокумента КАК Сумма
ИЗ
    Документ.ЗаказПоставщику КАК ЗаказПоставщику
ГДЕ
    ЗаказПоставщику.Проведен = ИСТИНА
УПОРЯДОЧИТЬ ПО
    ЗаказПоставщику.Дата УБЫВ""",
            ["Номер", "Дата", "Поставщик", "Сумма"],
        ),
    }

    titles = {
        "remains": "📋 <b>Остатки товаров на складе</b>",
        "deficit": "⚠️ <b>Дефицит: нулевые и отрицательные остатки</b>",
        "slow_moving": "🕰 <b>Залежалые позиции (большой остаток)</b>",
        "orders": "📦 <b>Последние заказы поставщикам</b>",
    }

    if report_type not in queries:
        await callback.answer("Неизвестный отчёт.")
        return

    await callback.message.edit_text("⏳ Загружаю данные из 1С…")
    await callback.answer()

    from ..bot import get_connector, get_llm_client, get_metadata_cache

    connector = get_connector()
    llm = get_llm_client()
    metadata = get_metadata_cache()

    if connector is None or not connector.is_connected:
        await callback.message.edit_text(
            "❌ Нет подключения к 1С.",
            reply_markup=_inventory_menu_kb(),
        )
        return

    query_text, cols = queries[report_type]
    title = titles[report_type]

    try:
        rows = await connector.execute_query(query_text, cols)
        if not rows:
            report_text = f"{title}\n\nДанных не найдено."
        else:
            lines = [title, ""]
            for i, row in enumerate(rows[:30], 1):
                parts = [f"{v}" for v in row.values()]
                lines.append(f"{i}. " + " | ".join(parts))
            report_text = "\n".join(lines)

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

    except Exception as exc:
        logger.error("Ошибка отчёта склада: %s", exc)
        report_text = f"❌ Ошибка получения данных:\n<code>{exc}</code>"

    await callback.message.edit_text(
        report_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К складу", callback_data="menu:inventory")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )

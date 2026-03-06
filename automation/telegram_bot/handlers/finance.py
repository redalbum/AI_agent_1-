# -*- coding: utf-8 -*-
"""
Обработчик раздела «Финансы».
Разделы: дебиторская задолженность, касса, расчёты с поставщиками.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

logger = logging.getLogger(__name__)
router = Router()


def _finance_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📈 Дебиторка", callback_data="finance:receivable"),
            InlineKeyboardButton(text="📉 Кредиторка", callback_data="finance:payable"),
        ],
        [
            InlineKeyboardButton(text="💵 Касса", callback_data="finance:cash"),
            InlineKeyboardButton(text="🏦 Банк", callback_data="finance:bank"),
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")],
    ])


@router.callback_query(F.data == "menu:finance")
async def finance_menu(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💰 <b>Финансы</b>\nВыберите отчёт:",
        reply_markup=_finance_menu_kb(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("finance:"))
async def finance_report(callback: CallbackQuery) -> None:
    report_type = callback.data.split(":")[1]

    queries: dict[str, tuple[str, list[str]]] = {
        "receivable": (
            """ВЫБРАТЬ ПЕРВЫЕ 30
    РасчетыСКлиентамиОстатки.Контрагент.Наименование КАК Контрагент,
    РасчетыСКлиентамиОстатки.СуммаОстаток КАК ДолгКлиента
ИЗ
    РегистрНакопления.РасчетыСКлиентами.Остатки AS РасчетыСКлиентамиОстатки
ГДЕ
    РасчетыСКлиентамиОстатки.СуммаОстаток > 0
УПОРЯДОЧИТЬ ПО
    ДолгКлиента УБЫВ""",
            ["Контрагент", "ДолгКлиента"],
        ),
        "payable": (
            """ВЫБРАТЬ ПЕРВЫЕ 30
    РасчетыСПоставщикамиОстатки.Контрагент.Наименование КАК Поставщик,
    РасчетыСПоставщикамиОстатки.СуммаОстаток КАК ДолгПоставщику
ИЗ
    РегистрНакопления.РасчетыСПоставщиками.Остатки AS РасчетыСПоставщикамиОстатки
ГДЕ
    РасчетыСПоставщикамиОстатки.СуммаОстаток > 0
УПОРЯДОЧИТЬ ПО
    ДолгПоставщику УБЫВ""",
            ["Поставщик", "ДолгПоставщику"],
        ),
        "cash": (
            """ВЫБРАТЬ
    ДенежныеСредстваОстатки.СчетУчета КАК Касса,
    ДенежныеСредстваОстатки.СуммаОстаток КАК Остаток
ИЗ
    РегистрНакопления.ДенежныеСредства.Остатки AS ДенежныеСредстваОстатки
УПОРЯДОЧИТЬ ПО
    Остаток УБЫВ""",
            ["Касса", "Остаток"],
        ),
        "bank": (
            """ВЫБРАТЬ
    ДенежныеСредствaBезналичныеОстатки.БанковскийСчет.Наименование КАК Счет,
    ДенежныеСредствaBезналичныеОстатки.СуммаОстаток КАК Остаток
ИЗ
    РегистрНакопления.ДенежныеСредстваБезналичные.Остатки AS ДенежныеСредствaBезналичныеОстатки
УПОРЯДОЧИТЬ ПО
    Остаток УБЫВ""",
            ["Счет", "Остаток"],
        ),
    }

    titles = {
        "receivable": "📈 <b>Дебиторская задолженность (долги клиентов)</b>",
        "payable": "📉 <b>Кредиторская задолженность (долги поставщикам)</b>",
        "cash": "💵 <b>Остатки в кассе</b>",
        "bank": "🏦 <b>Остатки на банковских счетах</b>",
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
            reply_markup=_finance_menu_kb(),
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
            total = 0.0
            for i, row in enumerate(rows[:30], 1):
                values = list(row.values())
                name = values[0] if values else "—"
                amount = values[1] if len(values) > 1 else "—"
                try:
                    amount_f = float(amount)
                    total += amount_f
                    amount_fmt = f"{amount_f:,.2f} ₽".replace(",", " ")
                except (ValueError, TypeError):
                    amount_fmt = str(amount)
                lines.append(f"{i}. {name} — {amount_fmt}")
            if total:
                lines.append(f"\n<b>Итого: {total:,.2f} ₽</b>".replace(",", " "))
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
        logger.error("Ошибка финансового отчёта: %s", exc)
        report_text = f"❌ Ошибка получения данных:\n<code>{exc}</code>"

    await callback.message.edit_text(
        report_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀️ К финансам", callback_data="menu:finance")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )

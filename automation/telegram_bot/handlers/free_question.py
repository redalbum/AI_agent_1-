# -*- coding: utf-8 -*-
"""
Обработчик раздела "Свободный вопрос".

Позволяет пользователю задать произвольный вопрос о базе данных.
LLM составляет запрос 1С, бот выполняет его и возвращает ответ.
"""

import logging
import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

import config
import llm_client
import metadata_scanner
import onec_connector
import prompts

logger = logging.getLogger(__name__)
router = Router()

_BACK = InlineKeyboardButton(text="◀️ Назад", callback_data="menu:main")
_CANCEL = InlineKeyboardButton(text="❌ Отмена", callback_data="free_question:cancel")


class FreeQuestionState(StatesGroup):
    waiting_for_question = State()


@router.callback_query(lambda c: c.data == "menu:free_question")
async def free_question_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await callback.answer("⛔ Нет доступа", show_alert=True)
        return

    await state.set_state(FreeQuestionState.waiting_for_question)
    await callback.message.edit_text(
        "💬 *Свободный вопрос*\n\n"
        "Задайте вопрос о вашей базе 1С на русском языке.\n\n"
        "*Примеры:*\n"
        "• Какая выручка за прошлую неделю?\n"
        "• Сколько товаров заканчивается?\n"
        "• Какой товар продаётся лучше всего?\n\n"
        "_Введите ваш вопрос:_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_CANCEL]]),
    )
    await callback.answer()


@router.callback_query(lambda c: c.data == "free_question:cancel")
async def free_question_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "📋 *Главное меню*\n\nВыберите раздел:",
        parse_mode="Markdown",
        reply_markup=_main_menu_keyboard(),
    )
    await callback.answer()


@router.message(FreeQuestionState.waiting_for_question, F.text)
async def free_question_answer(message: Message, state: FSMContext) -> None:
    if message.from_user.id not in config.TELEGRAM_ALLOWED_USERS:
        await message.answer("⛔ У вас нет доступа к этому боту.")
        await state.clear()
        return

    question = message.text.strip()
    await state.clear()

    status_msg = await message.answer("⏳ Составляю запрос к базе 1С...")

    # Получаем метаданные для формирования запроса
    cache = metadata_scanner.get_or_scan()
    metadata_summary = cache.summary_text()

    # LLM составляет запрос 1С
    query_text = await llm_client.ask(
        prompts.free_question_prompt(metadata_summary, question),
        system_message=prompts.SYSTEM_QUERY_BUILDER,
    )

    # Если LLM вернул ошибку
    if query_text.startswith("❌"):
        await status_msg.edit_text(
            f"❌ Не удалось составить запрос.\n\n{query_text}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    await status_msg.edit_text("⏳ Выполняю запрос к базе 1С...")

    # Подключаемся к 1С и выполняем запрос
    com_obj = onec_connector.connect(
        config.ONEC_CONNECTION_STRING, config.ONEC_USER, config.ONEC_PASSWORD
    )

    if com_obj is None:
        await status_msg.edit_text(
            "❌ Не удалось подключиться к базе 1С.\n"
            "Проверьте ONEC_CONNECTION_STRING в настройках.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
        )
        return

    # Извлекаем колонки из текста запроса (простая эвристика)
    cols = _extract_columns(query_text)
    rows = onec_connector.execute_query(com_obj, query_text, cols)
    data_text = _format_rows(rows) if rows else "Запрос не вернул данных."

    await status_msg.edit_text("⏳ Формирую ответ...")

    # LLM формулирует финальный ответ
    answer = await llm_client.ask(
        prompts.free_answer_prompt(question, data_text),
        system_message=prompts.SYSTEM_ANALYST,
    )

    await status_msg.edit_text(
        f"💬 *{question}*\n\n{answer}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[_BACK]]),
    )


def _extract_columns(query_text: str) -> list[str]:
    """Извлекает имена колонок из текста запроса 1С (эвристика по 'КАК ...')."""
    matches = re.findall(r'КАК\s+(\w+)', query_text, re.IGNORECASE)
    return list(dict.fromkeys(matches)) if matches else ["Значение"]


def _format_rows(rows: list[dict]) -> str:
    if not rows:
        return ""
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    lines.append("-" * len(lines[0]))
    for row in rows:
        lines.append(" | ".join(str(row.get(c, "")) for c in cols))
    return "\n".join(lines)


def _main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Аналитика продаж", callback_data="menu:analytics")],
        [InlineKeyboardButton(text="📦 Склад и остатки", callback_data="menu:inventory")],
        [InlineKeyboardButton(text="💰 Финансы", callback_data="menu:finance")],
        [InlineKeyboardButton(text="💬 Свободный вопрос", callback_data="menu:free_question")],
    ])

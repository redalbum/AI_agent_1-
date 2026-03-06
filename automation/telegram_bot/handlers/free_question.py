# -*- coding: utf-8 -*-
"""
Обработчик раздела «Свободный вопрос».
Пользователь вводит вопрос на естественном языке, LLM генерирует запрос 1С,
бот выполняет его и отвечает пользователю.
"""

from __future__ import annotations

import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)
router = Router()


class FreeQuestionStates(StatesGroup):
    waiting_for_question = State()


@router.callback_query(F.data == "menu:free_question")
async def free_question_start(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(FreeQuestionStates.waiting_for_question)
    await callback.message.edit_text(
        "💬 <b>Свободный вопрос к базе 1С</b>\n\n"
        "Напишите ваш вопрос на русском языке.\n"
        "Например: <i>«Какой товар продавался лучше всего в прошлом месяце?»</i>\n\n"
        "Для отмены нажмите кнопку ниже.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(FreeQuestionStates.waiting_for_question)
async def free_question_answer(message: Message, state: FSMContext) -> None:
    await state.clear()
    question = message.text or ""
    if not question.strip():
        await message.answer("Вопрос не может быть пустым.")
        return

    wait_msg = await message.answer("⏳ Обрабатываю запрос…")

    from ..bot import get_connector, get_llm_client, get_metadata_cache
    from ..metadata_scanner import MetadataScanner

    connector = get_connector()
    llm = get_llm_client()
    metadata = get_metadata_cache()

    if connector is None or not connector.is_connected:
        await wait_msg.edit_text(
            "❌ Нет подключения к 1С. Проверьте настройки.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    if llm is None:
        await wait_msg.edit_text(
            "❌ LLM-клиент не настроен. Проверьте PROVIDER_API_KEY.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
            ]),
        )
        return

    # Формируем контекст метаданных
    meta_text = ""
    if metadata:
        scanner = MetadataScanner(connector)
        meta_text = scanner.metadata_summary_text(metadata)

    try:
        # Шаг 1: LLM генерирует запрос 1С
        await wait_msg.edit_text("⏳ Генерирую запрос 1С…")
        query_1c = await llm.generate_query(question, meta_text)
        query_1c = query_1c.strip()

        # Очищаем от markdown-блоков если LLM добавил их
        if query_1c.startswith("```"):
            lines = query_1c.split("\n")
            query_1c = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            ).strip()

        # Шаг 2: Выполняем запрос в 1С
        await wait_msg.edit_text("⏳ Выполняю запрос в 1С…")
        rows = await connector.execute_query(query_1c)

        # Шаг 3: LLM анализирует результат
        if rows:
            data_text = f"Вопрос: {question}\n\nДанные из 1С:\n"
            for i, row in enumerate(rows[:50], 1):
                data_text += f"{i}. " + " | ".join(f"{k}: {v}" for k, v in row.items()) + "\n"
            await wait_msg.edit_text("⏳ Анализирую данные…")
            answer = await llm.analyze_data(data_text, meta_text)
        else:
            answer = "По вашему запросу данных не найдено."

        response_text = (
            f"💬 <b>Вопрос:</b> {question}\n\n"
            f"📊 <b>Ответ:</b>\n{answer}\n\n"
            f"🔍 <b>Запрос 1С:</b>\n<code>{query_1c[:500]}</code>"
        )

    except Exception as exc:
        logger.error("Ошибка свободного вопроса: %s", exc)
        response_text = (
            f"❌ Ошибка при обработке вопроса:\n<code>{exc}</code>\n\n"
            "Попробуйте переформулировать вопрос."
        )

    await wait_msg.edit_text(
        response_text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💬 Ещё вопрос", callback_data="menu:free_question")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main")],
        ]),
        parse_mode="HTML",
    )

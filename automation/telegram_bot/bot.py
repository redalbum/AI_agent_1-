# -*- coding: utf-8 -*-
"""
Главный файл Telegram-бота AI Бизнес-Ассистент для 1С.

Запуск:
    python bot.py

Требования:
    - Заполненный файл .env (скопируйте из .env.example)
    - Python 3.10+
    - Установленные зависимости: pip install -r requirements.txt
"""

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

# Загружаем конфигурацию первой — она вызывает load_dotenv()
try:
    import config
except ValueError as exc:
    print(f"\n❌ Ошибка конфигурации: {exc}")
    print("   Откройте файл .env и заполните все обязательные параметры.")
    sys.exit(1)

from handlers import (
    analytics_router,
    finance_router,
    free_question_router,
    inventory_router,
    start_router,
)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


async def main() -> None:
    logger.info("Запуск AI Бизнес-Ассистент для 1С...")

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    # Регистрируем обработчики
    dp.include_router(start_router)
    dp.include_router(analytics_router)
    dp.include_router(inventory_router)
    dp.include_router(finance_router)
    dp.include_router(free_question_router)

    logger.info("Бот запущен. Ожидаю сообщения...")
    print("\n   Бот работает! Откройте Telegram и напишите /start")
    print("   Для остановки нажмите Ctrl+C\n")

    try:
        await dp.start_polling(bot, allowed_updates=["message", "callback_query"])
    finally:
        await bot.session.close()
        logger.info("Бот остановлен.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n   Бот остановлен пользователем.")

@echo off
chcp 65001 >nul
title 🤖 AI Бизнес-Ассистент для 1С

cd /d "%~dp0"

echo.
echo ═══════════════════════════════════════════════════════════
echo    🤖 AI Бизнес-Ассистент для 1С
echo ═══════════════════════════════════════════════════════════
echo.

REM Проверка venv
if not exist "venv\Scripts\activate.bat" (
    echo ❌ Виртуальное окружение не найдено!
    echo    Сначала запустите INSTALL.bat
    pause
    exit /b 1
)

REM Проверка .env
if not exist ".env" (
    echo ❌ Файл .env не найден!
    echo    Скопируйте .env.example в .env и заполните настройки
    pause
    exit /b 1
)

REM Проверка что токен заполнен (содержит двоеточие — признак валидного токена)
findstr /R "^TELEGRAM_BOT_TOKEN=.*:.*" .env >nul 2>&1
if %errorLevel% neq 0 (
    echo ❌ TELEGRAM_BOT_TOKEN не заполнен или некорректен!
    echo    Откройте .env и укажите токен от @BotFather
    echo    Токен должен выглядеть как: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz
    pause
    exit /b 1
)

echo ✅ Конфигурация проверена
echo.
echo 🚀 Запускаю бота...
echo    Для остановки нажмите Ctrl+C или закройте окно
echo.

call venv\Scripts\activate.bat
python bot.py

echo.
echo 🛑 Бот остановлен
pause

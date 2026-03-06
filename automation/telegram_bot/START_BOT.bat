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

REM Проверка заполненности .env
findstr /C:"TELEGRAM_BOT_TOKEN=ваш_токен" .env >nul 2>&1
if %errorLevel% equ 0 (
    echo ❌ TELEGRAM_BOT_TOKEN не заполнен в .env!
    echo    Откройте .env и укажите токен от @BotFather
    pause
    exit /b 1
)
findstr /R "^TELEGRAM_BOT_TOKEN=$" .env >nul 2>&1
if %errorLevel% equ 0 (
    echo ❌ TELEGRAM_BOT_TOKEN не заполнен в .env!
    echo    Откройте .env и укажите токен от @BotFather
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

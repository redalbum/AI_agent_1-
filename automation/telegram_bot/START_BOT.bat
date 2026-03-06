@echo off
chcp 65001 >nul
title AI Бизнес-Ассистент для 1С

cd /d "%~dp0"

echo.
echo ===============================================================
echo    AI Бизнес-Ассистент для 1С
echo ===============================================================
echo.

REM Проверка .env
if not exist ".env" (
    echo [!] Файл .env не найден!
    echo     Сначала запустите INSTALL.bat
    pause
    exit /b 1
)

REM Проверка заполнения токена
findstr /C:"вставь-токен-сюда" .env >nul 2>&1
if %errorLevel% equ 0 (
    echo [!] Настройки не заполнены!
    echo     Откройте .env и заполните TELEGRAM_BOT_TOKEN
    pause
    exit /b 1
)

echo [OK] Активирую окружение...
call venv\Scripts\activate.bat

echo [OK] Запускаю бота...
echo.
echo      Бот работает! Откройте Telegram и напишите боту /start
echo      Для остановки нажмите Ctrl+C или закройте это окно
echo.
echo ---------------------------------------------------------------
echo.

python bot.py

pause

@echo off
chcp 65001 >nul
title Остановка AI Бизнес-Ассистент для 1С

echo.
echo ===============================================================
echo    Остановка AI Бизнес-Ассистент для 1С
echo ===============================================================
echo.

REM Завершаем процесс python, запускающий бота
taskkill /F /FI "WINDOWTITLE eq AI Бизнес-Ассистент для 1С*" /T >nul 2>&1
taskkill /F /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq AI*" /T >nul 2>&1

echo [OK] Бот остановлен.
echo.
pause

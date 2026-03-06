@echo off
chcp 65001 >nul
echo.
echo 🛑 Останавливаю AI Бизнес-Ассистент...
echo.

taskkill /F /IM python.exe /FI "WINDOWTITLE eq 🤖 AI Бизнес-Ассистент*" >nul 2>&1
if %errorLevel% equ 0 (
    echo ✅ Бот остановлен
) else (
    echo ⚠️  Бот не был запущен или уже остановлен
)

pause

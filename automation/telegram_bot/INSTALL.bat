@echo off
chcp 65001 >nul
title Установка AI Бизнес-Ассистент для 1С

echo.
echo ===============================================================
echo    Установщик AI Бизнес-Ассистент для 1С
echo ===============================================================
echo.

REM Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo [!] Требуются права администратора для установки Python
    echo     Перезапускаю с правами администратора...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo [1/6] Проверяю Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo       Python не найден. Скачиваю и устанавливаю...

    REM Скачивание Python через PowerShell
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"

    REM Тихая установка Python
    %TEMP%\python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1

    REM Обновление PATH
    set "PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"

    echo       Python установлен
) else (
    for /f "tokens=2" %%i in ('python --version') do echo       Найден Python %%i
)

echo.
echo [2/6] Создаю виртуальное окружение...
cd /d "%~dp0"
if exist "venv" (
    echo       venv уже существует, пропускаю...
) else (
    python -m venv venv
    echo       venv создан
)

echo.
echo [3/6] Активирую окружение и устанавливаю зависимости...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
pip install -r requirements.txt
echo       Зависимости установлены

echo.
echo [4/6] Создаю файл настроек .env...
if exist ".env" (
    echo       .env уже существует, не перезаписываю
) else (
    copy .env.example .env >nul
    echo       .env создан
)

echo.
echo [5/6] Создаю ярлыки на рабочем столе...
set "DESKTOP=%USERPROFILE%\Desktop"
set "SCRIPT_DIR=%~dp0"

REM Ярлык "Настройки бота"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\Nastroyki_bota.lnk'); $s.TargetPath = 'notepad.exe'; $s.Arguments = '%SCRIPT_DIR%.env'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"

REM Ярлык "Запустить бота"
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\Zapustit_bota.lnk'); $s.TargetPath = '%SCRIPT_DIR%START_BOT.bat'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()"

echo       Ярлыки созданы на рабочем столе

echo.
echo [6/6] Проверяю установку...
call venv\Scripts\activate.bat
python -c "import aiogram; print('       OK aiogram', aiogram.__version__)"
python -c "import dotenv; print('       OK python-dotenv')"

echo.
echo ===============================================================
echo    Установка завершена!
echo ===============================================================
echo.
echo    Следующие шаги:
echo.
echo    1. Откройте "Nastroyki_bota" на рабочем столе
echo    2. Заполните TELEGRAM_BOT_TOKEN (от @BotFather)
echo    3. Заполните TELEGRAM_ALLOWED_USERS (от @userinfobot)
echo    4. Заполните путь к базе 1С
echo    5. Заполните PROVIDER_API_KEY (от openrouter.ai)
echo    6. Сохраните файл и закройте
echo    7. Запустите "Zapustit_bota" на рабочем столе
echo.
echo ===============================================================
echo.
pause

@echo off
chcp 65001 >nul
title 🤖 Полная автоматическая установка AI Агент для 1С:Розница

echo.
echo ═══════════════════════════════════════════════════════════
echo    🤖 ПОЛНАЯ УСТАНОВКА: AI Агент для 1С:Розница 2.3
echo ═══════════════════════════════════════════════════════════
echo.

REM ─────────────────────────────────────────────────────────────
REM Переходим в каталог скрипта, чтобы относительные пути работали
REM ─────────────────────────────────────────────────────────────
cd /d "%~dp0"

REM ─────────────────────────────────────────────────────────────
REM [1/7] Проверка Python
REM ─────────────────────────────────────────────────────────────
echo [1/7] Проверяю Python...
python --version >nul 2>&1
if %errorLevel% neq 0 (
    echo        ❌ Python не найден. Скачиваю и устанавливаю...
    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.8/python-3.11.8-amd64.exe' -OutFile '%TEMP%\python_installer.exe'"
    if %errorLevel% neq 0 (
        echo        ❌ Ошибка загрузки Python. Проверьте подключение к интернету.
        pause
        exit /b 1
    )
    REM SHA256 для python-3.11.8-amd64.exe — при обновлении версии в Uri выше
    REM необходимо также обновить хеш ниже (взять с https://www.python.org/downloads/)
    powershell -Command "$hash = (Get-FileHash '%TEMP%\python_installer.exe' -Algorithm SHA256).Hash; if ($hash -ne '6EB2C88D05BB58B4A990EAB27A2F6A09E0FCBF1FCEA2906E3C43D55E4D1ED81B') { Remove-Item '%TEMP%\python_installer.exe'; Write-Error 'Ошибка: контрольная сумма не совпадает'; exit 1 }"
    if %errorLevel% neq 0 (
        echo        ❌ Ошибка проверки целостности файла. Установка прервана.
        pause
        exit /b 1
    )
    "%TEMP%\python_installer.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_pip=1
    if %errorLevel% neq 0 (
        echo        ❌ Не удалось установить Python. Установите вручную: https://www.python.org/downloads/
        pause
        exit /b 1
    )
    set "PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts"
    echo        ✅ Python установлен
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do echo        ✅ Python %%i
)
echo.

REM ─────────────────────────────────────────────────────────────
REM [2/7] Создание venv и установка зависимостей
REM ─────────────────────────────────────────────────────────────
echo [2/7] Устанавливаю зависимости...
if exist "venv\Scripts\activate.bat" (
    echo        ⚠️  venv уже существует, обновляю зависимости...
) else (
    python -m venv venv
    if %errorLevel% neq 0 (
        echo        ❌ Не удалось создать виртуальное окружение.
        pause
        exit /b 1
    )
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
if %errorLevel% neq 0 (
    echo        ❌ Ошибка установки зависимостей. Проверьте requirements.txt.
    pause
    exit /b 1
)
echo        ✅ Зависимости установлены
echo.

REM ─────────────────────────────────────────────────────────────
REM [3/7] — [7/7] Автоматическая настройка 1С
REM  Поиск платформы, выбор базы, загрузка расширения,
REM  настройка .env, проверка подключения
REM ─────────────────────────────────────────────────────────────
echo [3/7] Запускаю мастер настройки 1С...
echo.

REM Путь к auto_setup_1c.py находится на уровень выше (automation/)
python "%~dp0..\auto_setup_1c.py"
set SETUP_RC=%errorLevel%

if %SETUP_RC% neq 0 (
    echo.
    echo ═══════════════════════════════════════════════════════════
    echo    ❌ Установка завершилась с ошибкой (код %SETUP_RC%)
    echo ═══════════════════════════════════════════════════════════
    echo.
    echo    Возможные причины:
    echo    • 1С:Предприятие не установлено (установите платформу 8.3)
    echo    • База 1С заблокирована — закройте все сеансы и повторите
    echo    • Нет прав администратора конфигуратора
    echo    • Каталог xml/ не найден (запустите из корня проекта)
    echo.
    pause
    exit /b %SETUP_RC%
)

REM ─────────────────────────────────────────────────────────────
REM Ярлыки на рабочем столе
REM ─────────────────────────────────────────────────────────────
echo Создаю ярлыки на рабочем столе...
set "DESKTOP=%USERPROFILE%\Desktop"
set "SCRIPT_DIR=%~dp0"

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\⚙️ Настройки бота.lnk'); $s.TargetPath = 'notepad.exe'; $s.Arguments = '%SCRIPT_DIR%.env'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()" >nul 2>&1
powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%DESKTOP%\🚀 Запустить бота.lnk'); $s.TargetPath = '%SCRIPT_DIR%START_BOT.bat'; $s.WorkingDirectory = '%SCRIPT_DIR%'; $s.Save()" >nul 2>&1
echo        ✅ Ярлыки созданы на рабочем столе
echo.

echo ═══════════════════════════════════════════════════════════
echo    ✅ УСТАНОВКА ЗАВЕРШЕНА!
echo ═══════════════════════════════════════════════════════════
echo.
echo    Запустите бота: START_BOT.bat
echo    Или используйте ярлык на рабочем столе: 🚀 Запустить бота
echo.
pause

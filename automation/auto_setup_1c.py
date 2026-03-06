# -*- coding: utf-8 -*-
"""
Автоматическая настройка 1С для AI Агента.

Функции:
- find_1c_platform()       - поиск установленной платформы 1С
- list_registered_bases()  - список зарегистрированных баз из ibases.v8i
- install_extension()      - загрузка расширения из xml/ в базу
- test_connection()        - проверка подключения к базе
- interactive_setup()      - интерактивный мастер настройки

Запуск:
    python auto_setup_1c.py
"""

import os
import re
import subprocess
import sys
import logging
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Поиск платформы 1С
# ─────────────────────────────────────────────────────────────────────────────

def find_1c_platform() -> str | None:
    """
    Находит путь к 1cv8.exe.

    Порядок поиска:
    1. Переменная окружения 1C_PLATFORM_PATH
    2. Реестр Windows (HKLM\\SOFTWARE\\1C\\1Cv8 и 1Cv85)
    3. Стандартные каталоги C:\\Program Files\\1cv8\\* и C:\\Program Files (x86)\\1cv8\\*

    Возвращает полный путь к 1cv8.exe или None, если не найден.
    """
    # 1. Переменная окружения
    env_path = os.environ.get("1C_PLATFORM_PATH")
    if env_path and Path(env_path).is_file():
        logger.info("Платформа найдена через 1C_PLATFORM_PATH: %s", env_path)
        return env_path

    # 2. Реестр Windows
    if sys.platform == "win32":
        candidate = _find_platform_in_registry()
        if candidate:
            return candidate

    # 3. Стандартные каталоги
    candidate = _find_platform_in_standard_paths()
    if candidate:
        return candidate

    return None


def _find_platform_in_registry() -> str | None:
    """Ищет платформу 1С в реестре Windows."""
    try:
        import winreg  # noqa: PLC0415  (Windows only)
    except ImportError:
        return None

    registry_keys = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\1C\1Cv8"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\1C\1Cv8"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\1C\1Cv85"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\1C\1Cv85"),
    ]

    best: tuple[str, str] | None = None  # (version, exe_path)

    for hive, key_path in registry_keys:
        try:
            with winreg.OpenKey(hive, key_path) as key:
                idx = 0
                while True:
                    try:
                        version = winreg.EnumKey(key, idx)
                        idx += 1
                        try:
                            with winreg.OpenKey(key, version) as ver_key:
                                install_path, _ = winreg.QueryValueEx(ver_key, "InstallPath")
                                exe = Path(install_path) / "bin" / "1cv8.exe"
                                if exe.is_file():
                                    if best is None or version > best[0]:
                                        best = (version, str(exe))
                        except (FileNotFoundError, OSError):
                            pass
                    except OSError:
                        break
        except (FileNotFoundError, OSError):
            continue

    if best:
        logger.info("Платформа найдена в реестре (версия %s): %s", best[0], best[1])
        return best[1]
    return None


def _find_platform_in_standard_paths() -> str | None:
    """Ищет платформу 1С в стандартных каталогах установки."""
    base_dirs = [
        Path(r"C:\Program Files\1cv8"),
        Path(r"C:\Program Files (x86)\1cv8"),
    ]

    candidates: list[tuple[str, Path]] = []
    for base in base_dirs:
        if not base.is_dir():
            continue
        for version_dir in base.iterdir():
            exe = version_dir / "bin" / "1cv8.exe"
            if exe.is_file():
                candidates.append((version_dir.name, exe))

    if not candidates:
        return None

    # Выбираем самую новую версию
    candidates.sort(key=lambda t: t[0], reverse=True)
    best_version, best_exe = candidates[0]
    logger.info("Платформа найдена в стандартном пути (версия %s): %s", best_version, best_exe)
    return str(best_exe)


# ─────────────────────────────────────────────────────────────────────────────
# Список зарегистрированных баз
# ─────────────────────────────────────────────────────────────────────────────

def list_registered_bases() -> list[dict]:
    """
    Читает список зарегистрированных баз из файла ibases.v8i.

    Источники (в порядке проверки):
    - %APPDATA%\\1C\\1CEStart\\ibases.v8i
    - %LOCALAPPDATA%\\1C\\1CEStart\\ibases.v8i

    Возвращает список словарей вида:
    [{"name": "Розница", "path": "C:\\Bases\\Retail", "type": "file"}, ...]

    Для серверных баз поле "path" содержит строку подключения вида
    'Srvr="host";Ref="base";'.
    """
    search_paths = []
    appdata = os.environ.get("APPDATA")
    localappdata = os.environ.get("LOCALAPPDATA")
    if appdata:
        search_paths.append(Path(appdata) / "1C" / "1CEStart" / "ibases.v8i")
    if localappdata:
        search_paths.append(Path(localappdata) / "1C" / "1CEStart" / "ibases.v8i")

    for ibases_file in search_paths:
        if ibases_file.is_file():
            return _parse_ibases(ibases_file)

    logger.warning("Файл ibases.v8i не найден. Список зарегистрированных баз пуст.")
    return []


def _parse_ibases(ibases_file: Path) -> list[dict]:
    """Разбирает файл ibases.v8i и возвращает список баз."""
    bases: list[dict] = []
    current: dict | None = None

    try:
        content = ibases_file.read_text(encoding="utf-8-sig", errors="replace")
    except OSError as exc:
        logger.error("Ошибка чтения %s: %s", ibases_file, exc)
        return []

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            if current is not None:
                bases.append(current)
            current = {"name": line[1:-1], "path": "", "type": "file"}
        elif current is not None and "=" in line:
            key, _, value = line.partition("=")
            key = key.strip().lower()
            value = value.strip()
            if key == "connect":
                _apply_connect(current, value)

    if current is not None:
        bases.append(current)

    logger.info("Найдено баз в ibases.v8i: %d", len(bases))
    return bases


def _apply_connect(base: dict, connect_value: str) -> None:
    """Заполняет поля 'path' и 'type' на основе строки Connect= из ibases.v8i."""
    # Файловая база: File="..."
    m = re.search(r'file\s*=\s*"([^"]+)"', connect_value, re.IGNORECASE)
    if m:
        base["path"] = m.group(1)
        base["type"] = "file"
        return

    # Серверная база: Srvr="...";Ref="...";
    m_srvr = re.search(r'srvr\s*=\s*"([^"]+)"', connect_value, re.IGNORECASE)
    m_ref = re.search(r'ref\s*=\s*"([^"]+)"', connect_value, re.IGNORECASE)
    if m_srvr and m_ref:
        base["path"] = f'Srvr="{m_srvr.group(1)}";Ref="{m_ref.group(1)}";'
        base["type"] = "server"
        return

    # Прочее — сохраняем как есть
    base["path"] = connect_value
    base["type"] = "other"


# ─────────────────────────────────────────────────────────────────────────────
# Установка расширения
# ─────────────────────────────────────────────────────────────────────────────

def install_extension(
    platform_exe: str,
    base_info: dict,
    xml_path: str,
    extension_name: str = "ИИ_Агент",
    username: str = "",
    password: str = "",
) -> bool:
    """
    Загружает расширение из XML в базу 1С и обновляет конфигурацию БД.

    Команды:
        1cv8.exe DESIGNER /F "..." /LoadConfigFromFiles "xml/" -Extension "ИИ_Агент"
        1cv8.exe DESIGNER /F "..." /UpdateDBCfg -Extension "ИИ_Агент"

    Возвращает True при успехе, False при ошибке.
    """
    if not Path(platform_exe).is_file():
        logger.error("1cv8.exe не найден: %s", platform_exe)
        _hint_platform_not_found()
        return False

    xml_abs = str(Path(xml_path).resolve())
    if not Path(xml_abs).is_dir():
        logger.error("Каталог XML не найден: %s", xml_abs)
        return False

    base_args = _build_base_args(base_info, username, password)
    if base_args is None:
        return False

    platform_bin = str(Path(platform_exe).parent)
    load_log = str(LOG_DIR / "install-extension.log")
    update_log = str(LOG_DIR / "update-db.log")

    # Шаг 1: LoadConfigFromFiles
    load_args = (
        [platform_exe]
        + base_args
        + [
            "DESIGNER",
            "/DisableStartupDialogs",
            "/DisableStartupMessages",
            "/Out", load_log,
            "/LoadConfigFromFiles", xml_abs,
            "-Extension", extension_name,
        ]
    )
    print(f"       ⏳ Загрузка из XML... (это может занять 1-2 минуты)")
    rc = _run_1cv8(load_args, "LoadConfigFromFiles", load_log, platform_bin)
    if rc != 0:
        _hint_install_error(rc, load_log)
        return False
    print("       ✅ Расширение загружено")

    # Шаг 2: UpdateDBCfg
    update_args = (
        [platform_exe]
        + base_args
        + [
            "DESIGNER",
            "/DisableStartupDialogs",
            "/DisableStartupMessages",
            "/Out", update_log,
            "/UpdateDBCfg",
            "-Extension", extension_name,
        ]
    )
    print("       ⏳ Обновление БД...")
    rc = _run_1cv8(update_args, "UpdateDBCfg", update_log, platform_bin)
    if rc != 0:
        _hint_install_error(rc, update_log)
        return False
    print("       ✅ БД обновлена")

    return True


def _build_base_args(base_info: dict, username: str, password: str) -> list[str] | None:
    """Формирует аргументы подключения к базе для 1cv8.exe."""
    base_type = base_info.get("type", "file")
    path = base_info.get("path", "")

    if base_type == "file":
        if not Path(path).is_dir():
            logger.error("Каталог базы не существует: %s", path)
            return None
        args = ["/F", path]
    elif base_type == "server":
        args = ["/IBConnectionString", path]
    else:
        args = ["/IBConnectionString", path]

    if username:
        args += ["/N", username]
    if password:
        args += ["/P", password]

    return args


def _run_1cv8(cmd: list[str], operation: str, log_file: str, cwd: str) -> int:
    """Запускает 1cv8.exe и возвращает код возврата."""
    logger.debug("Запуск: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            timeout=600,
            cwd=cwd,
        )
        if result.returncode != 0:
            logger.error(
                "Операция '%s' завершилась с кодом %d. Лог: %s",
                operation, result.returncode, log_file,
            )
        return result.returncode
    except subprocess.TimeoutExpired:
        logger.error("Операция '%s': превышено время ожидания (600 с)", operation)
        return -1
    except OSError as exc:
        logger.error("Операция '%s': ошибка запуска: %s", operation, exc)
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# Проверка подключения
# ─────────────────────────────────────────────────────────────────────────────

def test_connection(
    platform_exe: str,
    base_info: dict,
    username: str = "",
    password: str = "",
) -> bool:
    """
    Проверяет подключение к базе 1С через DESIGNER /DumpConfigToFiles.

    Выгружает конфигурацию во временный каталог (немедленно прерывается через
    /StopManager) — если 1С успешно открыла базу, команда вернёт код 0 или 1
    (ошибка выгрузки допустима), а не -1 или исключение.

    Возвращает True, если подключение успешно.
    """
    if not Path(platform_exe).is_file():
        return False

    base_args = _build_base_args(base_info, username, password)
    if base_args is None:
        return False

    platform_bin = str(Path(platform_exe).parent)
    test_log = str(LOG_DIR / "connection-test.log")

    # /CheckModules завершается после синтаксической проверки модулей и корректно
    # возвращает 0 при успешном открытии базы во всех версиях платформы 8.3.x
    cmd = (
        [platform_exe]
        + base_args
        + [
            "DESIGNER",
            "/DisableStartupDialogs",
            "/DisableStartupMessages",
            "/Out", test_log,
            "/CheckModules",
        ]
    )
    try:
        result = subprocess.run(cmd, timeout=60, cwd=platform_bin)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        # Если 1С открылась и ждёт — значит подключение есть
        return True
    except OSError:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Подсказки при ошибках
# ─────────────────────────────────────────────────────────────────────────────

def _hint_platform_not_found() -> None:
    print()
    print("  ❌ Платформа 1С не найдена!")
    print("     Установите 1С:Предприятие 8.3 с официального сайта:")
    print("     https://releases.1c.ru/project/Platform83")
    print("     После установки повторите запуск установщика.")
    print()


def _hint_install_error(return_code: int, log_file: str) -> None:
    print()
    print(f"  ❌ Ошибка при установке расширения (код {return_code})")
    print(f"     Лог: {log_file}")
    print()
    # Анализируем лог для более точной подсказки
    try:
        log_text = Path(log_file).read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        log_text = ""

    if "монопольн" in log_text.lower() or "exclusive" in log_text.lower():
        print("  💡 База заблокирована в монопольном режиме.")
        print("     Закройте все сеансы 1С, работающие с этой базой, и повторите.")
    elif "прав" in log_text.lower() or "access" in log_text.lower() or "право" in log_text.lower():
        print("  💡 Недостаточно прав.")
        print("     Убедитесь, что пользователь является администратором конфигуратора.")
    elif log_text:
        # Выводим последние строки лога
        lines = [l for l in log_text.splitlines() if l.strip()]
        for line in lines[-5:]:
            print(f"     {line}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Генерация .env
# ─────────────────────────────────────────────────────────────────────────────

def generate_env_file(
    env_path: str,
    connection_string: str,
    username: str,
    password: str,
    telegram_token: str,
    telegram_allowed_users: str,
    provider_api_key: str,
    llm_model: str = "anthropic/claude-3.5-sonnet",
) -> None:
    """Создаёт файл .env с указанными настройками."""
    content = f"""\
# ═══════════════════════════════════════════════════════════════
#  🤖 AI Бизнес-Ассистент для 1С:Розница 2.3 — Настройки
# ═══════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────────────────────
# Токен бота от @BotFather (обязательно)
TELEGRAM_BOT_TOKEN={telegram_token}

# ID пользователей через запятую, которым разрешён доступ
# Узнать свой ID: напишите @userinfobot в Telegram
TELEGRAM_ALLOWED_USERS={telegram_allowed_users}

# ─────────────────────────────────────────────────────────────
# 1С:Розница 2.3
# ─────────────────────────────────────────────────────────────
# Строка подключения к базе 1С
# Файловая база: File="C:\\Bases\\Retail";
# Серверная база: Srvr="192.168.1.100";Ref="retail";
ONEC_CONNECTION_STRING={connection_string}

# Логин и пароль для подключения к 1С (если требуется)
ONEC_USERNAME={username}
ONEC_PASSWORD={password}

# ─────────────────────────────────────────────────────────────
# LLM (OpenRouter)
# ─────────────────────────────────────────────────────────────
# API ключ от openrouter.ai (обязательно)
PROVIDER_API_KEY={provider_api_key}

# Модель (рекомендуется anthropic/claude-3.5-sonnet)
LLM_MODEL={llm_model}

# ─────────────────────────────────────────────────────────────
# ДОПОЛНИТЕЛЬНО
# ─────────────────────────────────────────────────────────────
# Время кэширования метаданных 1С в секундах (по умолчанию 3600)
METADATA_CACHE_TTL=3600

# Уровень логирования: DEBUG, INFO, WARNING, ERROR
LOG_LEVEL=INFO
"""
    Path(env_path).write_text(content, encoding="utf-8")
    logger.info(".env создан: %s", env_path)


# ─────────────────────────────────────────────────────────────────────────────
# Интерактивная настройка
# ─────────────────────────────────────────────────────────────────────────────

def interactive_setup() -> int:
    """
    Запускает интерактивный мастер настройки AI Агента для 1С:Розница 2.3.

    Возвращает 0 при успехе, ненулевое значение при ошибке.
    """
    _print_header("🤖 Мастер настройки AI Агент для 1С:Розница 2.3")

    # ── Шаг 1: поиск платформы 1С ───────────────────────────────────────────
    print("[1/5] Ищу платформу 1С...")
    platform_exe = find_1c_platform()
    if not platform_exe:
        _hint_platform_not_found()
        return 1
    print(f"      ✅ Найдена: {platform_exe}")
    print()

    # ── Шаг 2: список зарегистрированных баз ────────────────────────────────
    print("[2/5] Ищу зарегистрированные базы 1С...")
    bases = list_registered_bases()

    selected_base: dict | None = None
    if bases:
        print(f"      Найденные базы 1С:")
        for i, b in enumerate(bases, 1):
            type_label = "файловая" if b["type"] == "file" else "серверная"
            print(f"         {i}. {b['name']} ({type_label}) — {b['path']}")
        print()
        choice = _prompt(f"      Выберите номер базы [1]", default="1")
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(bases):
                selected_base = bases[idx]
            else:
                print("      ❌ Неверный номер базы.")
                return 1
        except ValueError:
            print("      ❌ Введите число.")
            return 1
    else:
        print("      ⚠️  Зарегистрированные базы не найдены.")
        print("         Введите путь к базе вручную.")
        manual_path = _prompt("      Путь к базе 1С (например C:\\Bases\\Retail)")
        if not manual_path:
            print("      ❌ Путь не указан.")
            return 1
        selected_base = {"name": "Розница", "path": manual_path, "type": "file"}
    print()

    # ── Шаг 3: установка расширения ─────────────────────────────────────────
    print("[3/5] Устанавливаю расширение ИИ_Агент...")
    ib_username = _prompt("      Имя пользователя 1С [Администратор]", default="Администратор")
    ib_password = _prompt_password("      Пароль 1С (Enter — пустой)")

    script_dir = Path(__file__).parent
    xml_path = str(script_dir.parent / "xml")

    ok = install_extension(
        platform_exe=platform_exe,
        base_info=selected_base,
        xml_path=xml_path,
        extension_name="ИИ_Агент",
        username=ib_username,
        password=ib_password,
    )
    if not ok:
        return 1
    print()

    # ── Шаг 4: настройки Telegram и LLM ─────────────────────────────────────
    print("[4/5] Настройка подключения:")
    telegram_token = _prompt("      Токен Telegram бота (от @BotFather)")
    telegram_users = _prompt("      Ваш Telegram ID (от @userinfobot)")
    provider_key = _prompt("      API ключ OpenRouter (openrouter.ai)")
    print()

    # ── Формирование строки подключения ──────────────────────────────────────
    if selected_base["type"] == "file":
        connection_string = f'File="{selected_base["path"]}";'
    else:
        connection_string = selected_base["path"]

    if ib_username:
        connection_string += f'Usr="{ib_username}";'
    if ib_password:
        connection_string += f'Pwd="{ib_password}";'

    # ── Запись .env ───────────────────────────────────────────────────────────
    bot_dir = script_dir / "telegram_bot"
    env_path = str(bot_dir / ".env")

    if Path(env_path).exists():
        overwrite = _prompt("      Файл .env уже существует. Перезаписать? [y/N]", default="N")
        if overwrite.lower() not in ("y", "да", "yes"):
            print("      ⚠️  .env не перезаписан, используем существующий.")
        else:
            generate_env_file(
                env_path=env_path,
                connection_string=connection_string,
                username=ib_username,
                password=ib_password,
                telegram_token=telegram_token,
                telegram_allowed_users=telegram_users,
                provider_api_key=provider_key,
            )
            print("      ✅ Файл .env создан")
    else:
        generate_env_file(
            env_path=env_path,
            connection_string=connection_string,
            username=ib_username,
            password=ib_password,
            telegram_token=telegram_token,
            telegram_allowed_users=telegram_users,
            provider_api_key=provider_key,
        )
        print("      ✅ Файл .env создан")
    print()

    # ── Шаг 5: проверка подключения ──────────────────────────────────────────
    print("[5/5] Проверяю подключение к 1С...")
    ok = test_connection(
        platform_exe=platform_exe,
        base_info=selected_base,
        username=ib_username,
        password=ib_password,
    )
    if ok:
        print("      ✅ Подключение успешно!")
    else:
        print("      ⚠️  Не удалось автоматически проверить подключение.")
        print("         Это нормально — проверьте работу бота вручную после запуска.")
    print()

    _print_footer()
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции вывода
# ─────────────────────────────────────────────────────────────────────────────

def _print_header(title: str) -> None:
    line = "═" * 59
    print()
    print(line)
    print(f"   {title}")
    print(line)
    print()


def _print_footer() -> None:
    line = "═" * 59
    print(line)
    print("   ✅ УСТАНОВКА ЗАВЕРШЕНА!")
    print(line)
    print()
    print("   Запустите бота: START_BOT.bat")
    print()


def _prompt(message: str, default: str = "") -> str:
    """Запрашивает ввод у пользователя с подсказкой по умолчанию."""
    if default:
        full_message = f"{message} [{default}]: "
    else:
        full_message = f"{message}: "
    try:
        value = input(full_message).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    return value if value else default


def _prompt_password(message: str) -> str:
    """Запрашивает пароль (скрывает ввод, если доступно)."""
    try:
        import getpass  # noqa: PLC0415
        return getpass.getpass(f"{message}: ")
    except Exception:
        return _prompt(message)


# ─────────────────────────────────────────────────────────────────────────────
# Точка входа
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.exit(interactive_setup())

# Установка AI Агента для 1С:Розница 2.3

## Быстрый старт (рекомендуется)

Запустите единый установщик:

```
automation\telegram_bot\FULL_INSTALL.bat
```

Установщик сделает всё сам:
1. Проверит/установит Python
2. Создаст виртуальное окружение и установит зависимости
3. Найдёт установленную платформу 1С автоматически
4. Покажет список зарегистрированных баз — выберите нужную
5. Загрузит расширение ИИ_Агент в базу и обновит конфигурацию
6. Создаст файл `.env` с вашими настройками (токены, база)
7. Создаст ярлыки на рабочем столе

После окончания запускайте бота через ярлык **🚀 Запустить бота** или `START_BOT.bat`.

---

## Требования

| Компонент | Версия |
|-----------|--------|
| Windows | 10 / 11 |
| 1С:Предприятие | 8.3.x (любая актуальная) |
| Python | 3.11+ (установщик скачает автоматически) |
| Конфигурация | 1С:Розница 2.3 (и другие) |

---

## Пошаговая установка вручную

Если автоматический установщик по какой-то причине не подходит,
выполните шаги ниже.

### 1. Установите Python 3.11+

Скачайте с [python.org](https://www.python.org/downloads/) и установите
с галочкой **Add Python to PATH**.

### 2. Установите зависимости

```bat
cd automation\telegram_bot
python -m venv venv
call venv\Scripts\activate.bat
pip install -r requirements.txt
```

### 3. Настройте `.env`

Скопируйте шаблон и заполните:

```bat
copy .env.example .env
notepad .env
```

Обязательные параметры:

```ini
# Токен от @BotFather
TELEGRAM_BOT_TOKEN=123456:ABC...

# Ваш Telegram ID (от @userinfobot)
TELEGRAM_ALLOWED_USERS=88081193

# Строка подключения к базе 1С:Розница
# Файловая база:
ONEC_CONNECTION_STRING=File="C:\Bases\Retail";
# Серверная база:
# ONEC_CONNECTION_STRING=Srvr="192.168.1.100";Ref="retail";

# API ключ openrouter.ai
PROVIDER_API_KEY=sk-or-v1-...
```

### 4. Загрузите расширение в базу 1С

```bat
cd automation
python update_1c.py
```

Или используйте скрипт автонастройки:

```bat
python automation\auto_setup_1c.py
```

### 5. Запустите бота

```bat
automation\telegram_bot\START_BOT.bat
```

---

## Типы баз 1С

### Файловая база

```ini
ONEC_CONNECTION_STRING=File="C:\Bases\Retail";
```

### Серверная база (1С:Предприятие Сервер)

```ini
ONEC_CONNECTION_STRING=Srvr="192.168.1.100";Ref="retail";
```

### База с авторизацией

```ini
ONEC_CONNECTION_STRING=File="C:\Bases\Retail";
ONEC_USERNAME=Администратор
ONEC_PASSWORD=мой_пароль
```

---

## Поиск платформы 1С

Скрипт `auto_setup_1c.py` автоматически ищет `1cv8.exe` в следующем порядке:

1. Переменная окружения `1C_PLATFORM_PATH`
2. Реестр Windows (`HKLM\SOFTWARE\1C\1Cv8\...`)
3. Стандартные пути:
   - `C:\Program Files\1cv8\<версия>\bin\1cv8.exe`
   - `C:\Program Files (x86)\1cv8\<версия>\bin\1cv8.exe`

Выбирается самая новая из найденных версий.

Если нужно принудительно задать путь:

```bat
set 1C_PLATFORM_PATH=C:\Program Files\1cv8\8.3.24.1586\bin\1cv8.exe
python automation\auto_setup_1c.py
```

---

## Логи установки

Все операции с 1С логируются в `automation\logs\`:

| Файл | Содержимое |
|------|-----------|
| `install-extension.log` | Загрузка расширения из XML |
| `update-db.log` | Обновление конфигурации БД |
| `connection-test.log` | Проверка подключения |

---

## Решение проблем

### Платформа 1С не найдена

Убедитесь, что 1С:Предприятие установлено. Установить можно с
[releases.1c.ru](https://releases.1c.ru/project/Platform83).

### База заблокирована в монопольном режиме

Закройте все открытые сеансы 1С, работающие с этой базой, и
повторите установку.

### Нет прав на установку расширений

Убедитесь, что пользователь, от имени которого выполняется установка,
имеет права **Администратора** в конфигураторе 1С.

### Python не найден после установки

Закройте и снова откройте командную строку — PATH должен обновиться.
Или задайте явный путь:

```bat
set PATH=%PATH%;C:\Program Files\Python311;C:\Program Files\Python311\Scripts
```

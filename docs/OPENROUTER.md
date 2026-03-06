# 🌐 Настройка OpenRouter

[OpenRouter](https://openrouter.ai/) — агрегатор LLM-провайдеров с единым OpenAI-совместимым API. Удобен для работы из России, так как предоставляет доступ к моделям DeepSeek, Google Gemini, Anthropic Claude и другим.

## Быстрый старт

1. Зарегистрируйтесь на [openrouter.ai](https://openrouter.ai/).
2. Получите API-ключ в разделе [Keys](https://openrouter.ai/keys).
3. В настройках ИИ-агента (1С) укажите:
   - **Provider Base URL:** `https://openrouter.ai/api/v1`
   - **API Key:** ваш ключ OpenRouter
   - **Модель:** например, `deepseek/deepseek-chat`

## Доступные модели

| Модель | Описание |
| :--- | :--- |
| `deepseek/deepseek-chat` | DeepSeek V3 — мощная и экономичная модель |
| `google/gemini-2.0-flash-exp:free` | Google Gemini 2.0 Flash (бесплатный тариф) |
| `anthropic/claude-3.5-sonnet` | Anthropic Claude 3.5 Sonnet |
| `openai/gpt-4o` | OpenAI GPT-4o |
| `meta-llama/llama-3.3-70b-instruct` | Meta Llama 3.3 70B |

Полный список (300+) моделей: [openrouter.ai/models](https://openrouter.ai/models)

## HTTP-заголовки

OpenRouter поддерживает дополнительные заголовки для идентификации приложения (используются в статистике и для увеличения лимитов):

- `HTTP-Referer` — URL вашего приложения (например, `https://your-app.com`)
- `X-Title` — название вашего приложения (например, `1C AI Agent`)

Модуль `ИИА_Провайдеры` автоматически добавляет эти заголовки, если в `ПараметрыИИ` переданы свойства `OpenRouter_Referer` и `OpenRouter_Title`.

## Переменные окружения

```dotenv
PROVIDER_BASE_URL=https://openrouter.ai/api/v1
PROVIDER_API_KEY=sk-or-v1-...
PROVIDER_MODEL=deepseek/deepseek-chat

# Опциональные заголовки OpenRouter
OPENROUTER_REFERER=https://your-app.com
OPENROUTER_TITLE=1C AI Agent
```

## Запуск через Docker

```bash
cp .env.example .env
# Отредактируйте .env: укажите PROVIDER_API_KEY и другие параметры
docker compose up --build
```

## Сравнение провайдеров

| Критерий | Gitsell | OpenRouter | OpenAI напрямую |
| :--- | :--- | :--- | :--- |
| Доступность из РФ | ✅ | ✅ | ⚠️ (VPN) |
| Количество моделей | Несколько (~10) | 300+ | Только OpenAI |
| Бесплатный тариф | ✅ | ✅ (некоторые модели) | ❌ |
| Надёжность | Высокая | Высокая | Высокая |

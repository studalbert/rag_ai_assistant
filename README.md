# AI RAG Assistant

Учебно-портфолийный RAG-сервис: загрузка документов, фоновая индексация, семантический поиск и ответы LLM с указанием источников. Есть веб-интерфейс (HTMX) и Telegram-бот.

## Возможности

- Регистрация / логин (JWT access + refresh)
- Workspaces и загрузка PDF / DOCX / TXT / Markdown
- Фоновая обработка: извлечение текста → чанки → эмбеддинги → pgvector
- Чат с RAG и стримингом ответа (SSE)
- Лимиты использования и rate limiting
- Telegram-бот с привязкой аккаунта
- Sentry (опционально) и структурированные логи

## Архитектура

```text
                    ┌──────────────┐
                    │  Telegram    │
                    │  (aiogram)   │
                    └──────┬───────┘
                           │ HTTP
┌──────────┐        ┌──────▼───────┐        ┌─────────────┐
│  Browser │───────▶│  FastAPI API │───────▶│  PostgreSQL │
│  HTMX UI │        │  + JWT auth  │        │  + pgvector │
└──────────┘        └──────┬───────┘        └─────────────┘
                           │
                           │ tasks
                    ┌──────▼───────┐        ┌─────────────┐
                    │    Redis     │◀──────▶│ Celery      │
                    │  (broker)    │        │ worker      │
                    └──────────────┘        └──────┬──────┘
                                                   │
                                            extract/chunk/embed
```

**Слои backend**

| Слой | Путь | Ответственность |
|------|------|-----------------|
| API / Web | `app/api`, `app/web` | HTTP, валидация, коды ответов |
| Services | `app/services` | бизнес-логика |
| Repositories | `app/repositories` | доступ к БД |
| Models | `app/models` | SQLAlchemy-модели |
| Tasks | `app/tasks` | Celery: обработка документов |
| Bot | `bot/` | Telegram-клиент к тому же API |

Поток документа:

1. `POST /workspaces/{id}/documents` → файл на диск, запись `Document(status=pending)`
2. Celery-задача `process_document`
3. extract → chunk → embed → `chunks` + vector
4. `status=ready` или `failed`

Поток вопроса:

1. Проверка workspace и квот
2. Эмбеддинг вопроса → top-k в pgvector
3. Сборка промпта → стрим LLM (YandexGPT)
4. Сохранение Q/A в историю чата + source chunk ids

## Стек

- **API:** FastAPI, async SQLAlchemy 2, Alembic
- **БД:** PostgreSQL 16 + pgvector
- **Очередь:** Celery + Redis
- **LLM:** YandexGPT (OpenAI-compatible API)
- **Эмбеддинги:** `sentence-transformers` (`intfloat/multilingual-e5-base`)
- **Web:** Jinja2 + HTMX
- **Bot:** aiogram 3

## Быстрый старт

### Требования

- Docker + Docker Compose
- Ключи Yandex Cloud (LLM)
- (Опционально) токен Telegram-бота и Sentry DSN

### 1. Клонирование и env

```bash
git clone https://github.com/studalbert/rag_ai_assistant.git
cd rag_ai_assistant
cp env.example .env
```

Заполни минимум:

```env
# внутри docker-сети хост БД — db, не localhost
DATABASE_URL=postgresql+asyncpg://rag_user:rag_password@db:5432/rag_db
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=change-me-to-long-random-string

YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...

# опционально
TELEGRAM_BOT_TOKEN=...
SENTRY_DSN=
ENVIRONMENT=development
LOG_LEVEL=INFO
```

> В `env.example` для локального запуска вне Docker может быть указан `localhost`.
> Для `docker compose` используй хосты `db` и `redis`.

### 2. Запуск

```bash
docker compose up --build
```

Сервисы:

| Сервис | Назначение | Порт |
|--------|------------|------|
| `api` | FastAPI | 8000 |
| `worker` | Celery | — |
| `bot` | Telegram | — |
| `db` | Postgres + pgvector | 5432 |
| `redis` | брокер/кэш | 6379 |

### 3. Миграции

```bash
docker compose exec api alembic upgrade head
```

### 4. Проверка

- Health: http://localhost:8000/health
- Web UI: http://localhost:8000/web/login
- OpenAPI: http://localhost:8000/docs

## Основные сценарии

1. Зарегистрироваться на `/web/register`
2. Создать workspace
3. Загрузить документ (PDF/DOCX/TXT/MD) — статус `pending → processing → ready`
4. Открыть чат и задать вопрос — ответ со стримингом и источниками
5. (Опционально) привязать Telegram и спросить там же

## Тесты

```bash
docker compose exec api pytest -q
```

Внешние вызовы LLM/эмбеддингов в тестах мокаются.

## Структура репозитория

```text
app/
  api/           # JSON API роутеры
  web/           # HTMX-страницы
  core/          # config, db, security, logging, sentry, rate_limit
  models/
  repositories/
  schemas/
  services/      # auth, documents, chat, llm, embeddings, chunking...
  tasks/         # Celery
  templates/
bot/             # Telegram-бот
migrations/
tests/
docker-compose.yml
dockerfile
env.example
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | async SQLAlchemy URL |
| `REDIS_URL` | Redis для Celery |
| `JWT_SECRET_KEY` | секрет подписи JWT |
| `YANDEX_API_KEY` / `YANDEX_FOLDER_ID` | доступ к YandexGPT |
| `YANDEX_GPT_MODEL` | по умолчанию `yandexgpt-lite` |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | чанкинг |
| `DAILY_QUESTION_LIMIT` / `MAX_DOCUMENTS_PER_USER` | квоты тарифа |
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` / `LLM_RETRY_BASE_DELAY` | устойчивость LLM |
| `TELEGRAM_BOT_TOKEN` | бот |
| `SENTRY_DSN` | пусто = Sentry выключен |
| `ENVIRONMENT` / `LOG_LEVEL` | окружение и уровень логов |

## Наблюдаемость

- Логи: stdout контейнеров (`api`, `worker`)
- Sentry: включается при непустом `SENTRY_DSN`
- Ключевые события: login/register, upload, processing started/failed/finished, ошибки LLM

## Ограничения MVP

- Файлы на локальном диске (volume), не S3
- Эмбеддинги считаются в worker (CPU)
- Оплата/подписка — заглушка через квоты, без Stripe
- Google OAuth — по ТЗ опционален / может быть не завершён

## Лицензия

Учебный проект. Можно свободно использовать как референс для портфолио.

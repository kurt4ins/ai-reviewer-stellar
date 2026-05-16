# Stellar — AI Code Reviewer

> Автоматический security-ревью pull request'ов с inline-фиксами в один клик.

Stellar подключается к репозиторию как обычный коллабораторский аккаунт. На каждый PR в GitHub или GitLab он за 1–2 минуты:

1. забирает diff,
2. прогоняет каждый ханк через LLM-пайплайн (classifier → analyzer → critic),
3. оставляет inline-комментарии прямо в дифе с описанием уязвимости и готовым `suggestion`-блоком, который автор PR применяет одной кнопкой.

---

## Что умеет

- ✅ **Webhook-приём PR** от GitHub (HMAC-SHA256) и GitLab (token)
- ✅ **Двухмодельный LLM-пайплайн**: дешёвый classifier отсеивает чистые ханки, умный analyzer верифицирует и пишет fix-код
- ✅ **Tool use**: analyzer может запросить полный файл из репо для контекста
- ✅ **Critic-фильтр**: детерминированный пост-фильтр против галлюцинаций (дедуп, `confidence ≥ 0.7`, валидация диапазона строк)
- ✅ **15 CWE** с привязкой к языкам (SQLi, XSS, RCE, path traversal, hardcoded creds и др.)
- ✅ **Inline-комментарии** в нативном формате провайдера, с `suggestion`-блоком для one-click apply
- ✅ **Бот-аккаунт модель**: один токен на провайдера в `.env`, никакого шифрования per-repo
- ✅ **Фильтр файлов**: README, lock-файлы, картинки, `node_modules` и т.п. не уезжают в LLM

---

## Архитектура

```
 GitHub / GitLab ──webhook──▶ FastAPI (:8000)
                                  │
                                  ▼
                            Redis + ARQ queue
                                  │
                                  ▼
                            ARQ Worker (max_jobs=4)
                            ├─▶ PostgreSQL 16
                            ├─▶ OpenRouter LLM
                            └─▶ Git Provider API (inline comments)
```

| Слой     | Стек                                                                |
| -------- | ------------------------------------------------------------------- |
| Backend  | Python 3.12, FastAPI, SQLAlchemy 2.x async, ARQ, uv                 |
| БД       | PostgreSQL 16, Alembic                                              |
| Очередь  | Redis 7, ARQ                                                        |
| LLM      | OpenRouter (`deepseek-v4-flash` classifier, `qwen3-coder` analyzer) |
| Frontend | React 18, Vite, TypeScript, shadcn/ui, TanStack Query               |

---

## Структура

```
backend/app/
  api/webhooks.py          ─ /webhook/github, /webhook/gitlab
  providers/
    base.py                ─ GitProvider ABC + dataclasses
    github.py              ─ GitHub impl (diff, file, search, post comment)
    gitlab.py              ─ GitLab impl (с двухшаговым diff_refs)
  llm/
    pipeline.py            ─ оркестрация classifier→analyzer→critic
    prompts.py             ─ системные промпты
    tools.py               ─ tool use (get_file_context)
    comment_format.py      ─ рендер inline-комментария
    client.py              ─ AsyncOpenAI клиент (OpenRouter)
  workers/review.py        ─ ARQ WorkerSettings + review_pull_request
  utils/
    diff_parser.py         ─ unified diff → Hunk[]
    file_filter.py         ─ дефолтные ignore-globs + per-repo
  security/
    cwe_list.py            ─ каталог из 15 CWE с language mapping
  db/
    models.py              ─ User, Repository, Review, Finding, ReviewThread
    session.py             ─ async SQLAlchemy session
  config.py                ─ Pydantic Settings
  main.py                  ─ FastAPI entrypoint
backend/tests/             ─ 98 pytest, ruff clean
backend/scripts/seed_repo.py ─ зарегистрировать репу в БД
frontend/                  ─ React admin UI (WIP)
docker-compose.yml         ─ postgres + redis + backend + worker
```

---

## Быстрый старт

### Требования

- Docker + docker compose
- (для локальной разработки backend без контейнера) Python 3.12 + [uv](https://docs.astral.sh/uv/)

### 1. Поднять инфру и сервисы

```bash
docker compose up -d
```

Поднимется postgres, redis, backend (FastAPI на `:8000`) и worker. Миграции применяются автоматически на старте backend.

### 2. Создать бот-аккаунт и положить токен в `.env`

В корне проекта создай `.env`:

```env
# Bot user PATs
GITHUB_BOT_TOKEN=ghp_xxx
GITLAB_BOT_TOKEN=glpat-xxx

# OpenRouter
OPENROUTER_API_KEY=sk-or-v1-xxx
DEFAULT_CLASSIFIER_MODEL=deepseek/deepseek-v4-flash:free
DEFAULT_ANALYZER_MODEL=qwen/qwen3-coder:free

# Postgres / Redis (для запуска backend с хоста, не из контейнера)
POSTGRES_HOST=localhost
REDIS_URL=redis://localhost:6379/0

WEBHOOK_BASE_URL=https://your-public-url.example
LOG_LEVEL=INFO
```

### 3. Зарегистрировать репозиторий через UI

Открой `http://localhost:5173`, залогинься и добавь репу на странице **Repositories** — укажи `provider`, `owner`, `name`, `webhook_secret`.

Альтернатива через CLI (без UI):

```bash
docker compose exec backend uv run python -m scripts.seed_repo \
  --provider github/gitlab \
  --owner your-org \
  --name your-repo \
  --secret YOUR_WEBHOOK_SECRET
```

### 4. Настроить webhook у провайдера

**GitHub** → Settings → Webhooks → Add webhook:

- Payload URL: `https://your-public-url.example/webhook/github`
- Content type: `application/json`
- Secret: `YOUR_WEBHOOK_SECRET`
- Events: **Pull requests**

**GitLab** → Settings → Webhooks:

- URL: `https://your-public-url.example/webhook/gitlab`
- Secret token: `YOUR_WEBHOOK_SECRET`
- Trigger: **Merge request events**

### 5. Пригласить бот-аккаунт в репу

GitHub → Settings → Collaborators → пригласить бот-юзера с правом `write` (нужно для постинга review comments).

### 6. Открыть PR → готово

В течение 1–2 минут в дифе появятся inline-комментарии от бота.

---

## Локальная разработка

```bash
# Только инфра
docker compose up -d postgres redis

# Backend в reload-режиме
cd backend
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Worker
uv run arq app.workers.review.WorkerSettings

# Тесты + линт
uv run pytest
uv run ruff check .
```

### Миграции

```bash
uv run alembic revision --autogenerate -m "описание"
uv run alembic upgrade head
uv run alembic downgrade -1
```

### Probe-скрипт пайплайна (без webhook)

```bash
uv run python -m backend.scripts.probe_pipeline
```

Прогоняет встроенные семпл-патчи через classifier→analyzer→critic, удобно для отладки промптов.

---

## Как работает пайплайн

```
hunk + CWE catalog
       │
       ▼
┌─────────────────┐
│  CLASSIFIER     │   fast cheap LLM, JSON mode
│  status: clean/ │
│  found/unsure   │
└─────────────────┘
       │
       ▼ (если не clean)
┌─────────────────┐
│  ANALYZER       │   smart LLM + tool use
│  + fix_code     │   (может запросить get_file_context)
└─────────────────┘
       │
       ▼
┌─────────────────┐
│  CRITIC         │   detеrministic Python filter
│  confidence≥0.7 │   dedup, валидация диапазона
└─────────────────┘
       │
       ▼
   inline comments via provider API
```

Все промпты — в [backend/app/llm/prompts.py](backend/app/llm/prompts.py). Текст находок генерируется на русском, `fix_code` — на языке исходника.

---

## Каталог CWE

15 классов в [backend/app/security/cwe_list.py](backend/app/security/cwe_list.py):

| Critical                      | High                                  | Medium                     |
| ----------------------------- | ------------------------------------- | -------------------------- |
| CWE-89 SQL Injection          | CWE-79 XSS                            | CWE-327 Weak Crypto        |
| CWE-78 OS Command Injection   | CWE-22 Path Traversal                 | CWE-200 Info Exposure      |
| CWE-502 Deserialization       | CWE-611 XXE                           | CWE-1004 Cookie Flags      |
| CWE-94 Code Injection         | CWE-352 CSRF                          | CWE-377 Insecure Temp File |
| CWE-798 Hardcoded Credentials | CWE-918 SSRF, CWE-295 Cert Validation |                            |

Каждый CWE привязан к списку языков — XSS не предлагается в python-CLI, SQLi не ищется в CSS.

---

## Тесты

```bash
cd backend
uv run pytest -q
```

Покрытие: webhook signature verification, event parsing, provider API (mock через httpx `MockTransport`), diff parser, file filter, LLM tool use, analyzer/classifier response parsing, critic filter, comment formatting, worker end-to-end.

# src_postgres (хранение)

## Что хранится в Postgres

Postgres используется для:

- сессий и аудита (`sessions`, `intents`, `events`, `artifacts`)
- runtime состояния агента (`runtime_state`)
- кэша идемпотентности по request_id (`runtime_requests`)
- внутренних таблиц n8n (schema `n8n`)

## Миграции

Миграции находятся в:

- `src_postgres/data/migrations/`

Ключевые файлы:

- `001_bootstrap.sql`: базовая схема (sessions/events/etc)
- `003_runtime_state.sql`: `runtime_state` и `runtime_requests`
- `004_n8n_schema.sql`: создаёт schema `n8n`

## Таблицы runtime state

`runtime_state`:

- `session_id` (PK)
- `version` (optimistic locking)
- `active_workflow_id` (продолжение workflow)
- `pending` (user-in-the-loop)
- `context` (опциональный контекст workflow)

`runtime_requests`:

- `request_id` (PK)
- `session_id`, `trace_id`
- `status`, `response` (закэшированный `N8nRunResponse`)

# src_postgres

Postgres хранит:

- `sessions`, `events`, `artifacts` — общие данные сессий.
- `runtime_state` — состояние диалога по `session_id`.

## Миграции

Файлы: `src_postgres/data/migrations/*.sql`

- `001_bootstrap.sql`
- `002_core_schema.sql`
- `003_runtime_state.sql`
- `004_drop_runtime_requests.sql`

## runtime_state

- `session_id` (PK)
- `version` (optimistic locking)
- `active_workflow_id`
- `pending`
- `context`

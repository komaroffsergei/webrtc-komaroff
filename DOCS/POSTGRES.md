# src_postgres

## Responsibility
`src_postgres` provides the single PostgreSQL storage for the whole stack.
It stores chat sessions, workflow runtime state, and chat history.
It does not execute business logic.

## Schema (authoritative)
Only these tables are used by services:

### `sessions`
Purpose: one row per chat session.

- `session_id uuid primary key`: stable session identifier shared across services.
- `user_id text not null`: logical user ID (`user123` by default).
- `status text not null`: session lifecycle (`RUNNING`, `DONE`, `FAILED`, etc.).
- `created_at timestamptz not null default now()`: session creation timestamp.
- `updated_at timestamptz not null default now()`: last update timestamp.

Indexes:
- `sessions_user_idx (user_id)`

### `runtime_state`
Purpose: stateful LangGraph/runtime memory and pending workflow state per session.

- `session_id uuid primary key references sessions(session_id) on delete cascade`: owner session.
- `version int not null default 1`: optimistic lock version.
- `active_workflow_id text null`: currently active workflow ID.
- `pending jsonb null`: partially collected workflow parameters.
- `context jsonb null`: compact dialog memory (`summary + recent_turns`) and extra runtime context.
  - Includes:
    - `dialog_memory.summary`
    - `dialog_memory.recent_turns`
    - `artifact_memory` (latest structured entities/artifacts for contextual follow-up questions)
- `updated_at timestamptz not null default now()`: last state update timestamp.

Indexes:
- `runtime_state_updated_idx (updated_at)`

### `events`
Purpose: append-only chat history (user/assistant turns).

- `event_id bigserial primary key`: monotonic ordering key.
- `session_id uuid not null references sessions(session_id) on delete cascade`: owner session.
- `turn_id uuid not null`: stable turn ID used by UI/edit flow.
- `role text not null`: `user` or `assistant`.
- `text text not null`: message body.
- `meta jsonb null`: technical metadata (request IDs, status, linked user turn ID).
- `created_at timestamptz not null default now()`: event timestamp.

Indexes:
- `events_session_turn_uidx (session_id, turn_id)` unique
- `events_session_event_idx (session_id, event_id)`
- `events_session_created_idx (session_id, created_at)`

Removed legacy tables:
- `artifacts`
- `intents`
- `runtime_requests`

## Initialization and migrations
Init SQL:
- `src_postgres/data/init/010_core_schema.sql`

Migrations:
- `src_postgres/data/migrations/001_bootstrap.sql`
- `src_postgres/data/migrations/002_core_schema.sql`
- `src_postgres/data/migrations/003_runtime_state.sql`
- `src_postgres/data/migrations/004_drop_runtime_requests.sql`
- `src_postgres/data/migrations/005_chat_schema_cleanup.sql`

Container entrypoint applies all migrations on startup:
- `docker/postgres/entrypoint-with-migrations.sh`

## Run/stop
Docker:
```bash
cd docker
docker compose up -d src_postgres
docker compose stop src_postgres
```

## Common issues
- `relation "runtime_state" does not exist`
  - Cause: migrations were not applied.
  - Fix: recreate/start `src_postgres` and check migration logs.
- `duplicate key value violates unique constraint events_session_turn_uidx`
  - Cause: repeated insert with same `turn_id` for same `session_id`.
  - Fix: expected for edit flow; use UPSERT logic from `src_agent/utils/db.py`.

## Code pointers
- `src_postgres/data/init/010_core_schema.sql`
- `src_postgres/data/migrations/001_bootstrap.sql`
- `src_postgres/data/migrations/003_runtime_state.sql`
- `src_postgres/data/migrations/005_chat_schema_cleanup.sql`
- `docker/postgres/entrypoint-with-migrations.sh`

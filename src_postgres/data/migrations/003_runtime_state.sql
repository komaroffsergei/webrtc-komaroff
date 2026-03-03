-- 003_runtime_state.sql
-- Runtime state persisted for workflow orchestration (idempotent).

create table if not exists runtime_state (
  session_id uuid primary key references sessions(session_id) on delete cascade,
  version int not null default 1,
  active_workflow_id text null,
  pending jsonb null,
  context jsonb null,
  updated_at timestamptz not null default now()
);

create index if not exists runtime_state_updated_idx
  on runtime_state(updated_at);

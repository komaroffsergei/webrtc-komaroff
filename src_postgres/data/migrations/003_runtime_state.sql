-- 003_runtime_state.sql
-- Runtime state persisted for n8n orchestration (idempotent).

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

create table if not exists runtime_requests (
  request_id uuid primary key,
  session_id uuid not null references sessions(session_id) on delete cascade,
  trace_id uuid not null,
  status text not null,
  response jsonb null,
  created_at timestamptz not null default now()
);

create index if not exists runtime_requests_session_created_idx
  on runtime_requests(session_id, created_at);


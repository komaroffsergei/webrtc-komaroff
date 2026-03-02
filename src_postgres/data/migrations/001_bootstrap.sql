-- 001_bootstrap.sql
-- Guaranteed base schema (idempotent).

create table if not exists sessions (
  session_id   uuid primary key,
  user_id      text not null,
  status       text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists sessions_user_idx
  on sessions(user_id);

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

create table if not exists events (
  event_id    bigserial primary key,
  session_id  uuid not null references sessions(session_id) on delete cascade,
  turn_id     uuid not null,
  role        text not null,
  text        text not null,
  meta        jsonb null,
  created_at  timestamptz not null default now()
);

alter table events add column if not exists turn_id uuid;
alter table events add column if not exists role text;
alter table events add column if not exists text text;
alter table events add column if not exists meta jsonb;
alter table events add column if not exists created_at timestamptz not null default now();

create unique index if not exists events_session_turn_uidx
  on events(session_id, turn_id);

create index if not exists events_session_event_idx
  on events(session_id, event_id);

create index if not exists events_session_created_idx
  on events(session_id, created_at);

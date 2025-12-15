-- sessions
create table if not exists sessions (
  session_id   uuid primary key,
  user_id      text not null,
  status       text not null check (status in ('RUNNING','WAITING_USER','DONE')),
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

-- intents
create table if not exists intents (
  intent_id    uuid primary key,
  session_id   uuid not null references sessions(session_id) on delete cascade,
  intent_type  text not null,
  status       text not null check (status in ('RUNNING','DONE')),
  created_at   timestamptz not null default now()
);

-- artifacts
create table if not exists artifacts (
  artifact_id  uuid primary key,
  session_id   uuid not null references sessions(session_id) on delete cascade,
  intent_id    uuid references intents(intent_id) on delete set null,
  type         text not null,
  name         text not null,
  data         jsonb not null,
  created_at   timestamptz not null default now()
);

create index if not exists artifacts_session_type_idx
  on artifacts(session_id, type);

-- events
create table if not exists events (
  event_id    bigserial primary key,

  session_id  uuid not null references sessions(session_id) on delete cascade,
  intent_id   uuid references intents(intent_id) on delete set null,

  seq         int not null,
  role        text not null check (role in ('USER','LLM','TOOL','SYSTEM')),
  event_type  text not null,
  name        text,

  input       jsonb,
  output      jsonb,

  created_at  timestamptz not null default now()
);

create unique index if not exists events_session_seq_idx
  on events(session_id, seq);

create index if not exists events_intent_idx
  on events(intent_id);

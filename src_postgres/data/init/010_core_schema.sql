-- sessions
create table if not exists sessions (
  session_id   uuid primary key,
  user_id      text not null,
  status       text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists sessions_user_idx
  on sessions(user_id);

-- intents
create table if not exists intents (
  intent_id    uuid primary key,
  session_id   uuid not null references sessions(session_id) on delete cascade,
  intent_type  text not null,
  status       text not null,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create index if not exists intents_session_idx
  on intents(session_id);

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

create index if not exists artifacts_intent_idx
  on artifacts(intent_id);

-- events
create table if not exists events (
  event_id    bigserial primary key,

  session_id  uuid not null references sessions(session_id) on delete cascade,
  intent_id   uuid references intents(intent_id) on delete set null,

  role        text not null,      -- USER | LLM | TOOL | SYSTEM
  event_type  text not null,      -- MESSAGE | STEP_START | ... | ERROR | FINAL_RESPONSE
  name        text,               -- tool name / model / whatever label

  input       jsonb,
  output      jsonb,

  created_at  timestamptz not null default now()
);

create index if not exists events_session_created_idx
  on events(session_id, created_at);

create index if not exists events_intent_idx
  on events(intent_id);

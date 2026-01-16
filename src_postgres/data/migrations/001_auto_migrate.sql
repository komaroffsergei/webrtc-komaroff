-- 001_auto_migrate.sql
-- Idempotent "best effort" migrations.
-- Goal: keep data, avoid dropping tables, only additive changes + safe cleanup.

-- 1) sessions: add updated_at if missing, relax status checks if any old ones exist
do $$
declare
  c_name text;
begin
  -- Drop any CHECK constraint on sessions.status (old schema had it).
  select conname into c_name
  from pg_constraint
  where conrelid = 'sessions'::regclass
    and contype = 'c'
    and pg_get_constraintdef(oid) like '%status%';

  if c_name is not null then
    execute format('alter table sessions drop constraint %I', c_name);
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_name='sessions' and column_name='updated_at'
  ) then
    alter table sessions add column updated_at timestamptz not null default now();
  end if;
end $$;

-- 2) intents: ensure updated_at exists, relax status checks if any
do $$
declare
  c_name text;
begin
  select conname into c_name
  from pg_constraint
  where conrelid = 'intents'::regclass
    and contype = 'c'
    and pg_get_constraintdef(oid) like '%status%';

  if c_name is not null then
    execute format('alter table intents drop constraint %I', c_name);
  end if;

  if not exists (
    select 1 from information_schema.columns
    where table_name='intents' and column_name='updated_at'
  ) then
    alter table intents add column updated_at timestamptz not null default now();
  end if;
end $$;

-- 3) events: drop seq + unique index if old schema exists
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name='events' and column_name='seq'
  ) then
    drop index if exists events_session_seq_idx;
    alter table events drop column seq;
  end if;
end $$;

-- 4) ensure indexes exist (safe)
create index if not exists events_session_created_idx
  on events(session_id, created_at);

create index if not exists sessions_user_idx
  on sessions(user_id);

create index if not exists intents_session_idx
  on intents(session_id);

create index if not exists artifacts_intent_idx
  on artifacts(intent_id);

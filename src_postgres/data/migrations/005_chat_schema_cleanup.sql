-- 005_chat_schema_cleanup.sql
-- Consolidate schema to sessions + runtime_state + events.

drop table if exists artifacts;
drop table if exists intents;

do $$
begin
  if not exists (
    select 1 from information_schema.tables
    where table_name = 'events'
  ) then
    create table events (
      event_id    bigserial primary key,
      session_id  uuid not null references sessions(session_id) on delete cascade,
      turn_id     uuid not null,
      role        text not null,
      text        text not null,
      meta        jsonb null,
      created_at  timestamptz not null default now()
    );
  end if;
end $$;

alter table events add column if not exists turn_id uuid;
alter table events add column if not exists role text;
alter table events add column if not exists text text;
alter table events add column if not exists meta jsonb;
alter table events add column if not exists created_at timestamptz not null default now();

update events
set turn_id = (
  substr(md5(session_id::text || ':' || event_id::text), 1, 8) || '-' ||
  substr(md5(session_id::text || ':' || event_id::text), 9, 4) || '-' ||
  substr(md5(session_id::text || ':' || event_id::text), 13, 4) || '-' ||
  substr(md5(session_id::text || ':' || event_id::text), 17, 4) || '-' ||
  substr(md5(session_id::text || ':' || event_id::text), 21, 12)
)::uuid
where turn_id is null;

update events
set role = coalesce(nullif(trim(role), ''), 'SYSTEM')
where role is null or trim(role) = '';

do $$
declare
  has_output boolean;
  has_input boolean;
begin
  select exists (
    select 1 from information_schema.columns
    where table_name = 'events' and column_name = 'output'
  ) into has_output;
  select exists (
    select 1 from information_schema.columns
    where table_name = 'events' and column_name = 'input'
  ) into has_input;

  if has_output and has_input then
    execute 'update events set text = coalesce(text, output->>''text'', input->>''text'', '''') where text is null';
  elsif has_output then
    execute 'update events set text = coalesce(text, output->>''text'', '''') where text is null';
  elsif has_input then
    execute 'update events set text = coalesce(text, input->>''text'', '''') where text is null';
  else
    execute 'update events set text = coalesce(text, '''') where text is null';
  end if;
end $$;

alter table events alter column turn_id set not null;
alter table events alter column role set not null;
alter table events alter column text set not null;

alter table events drop column if exists intent_id;
alter table events drop column if exists event_type;
alter table events drop column if exists name;
alter table events drop column if exists input;
alter table events drop column if exists output;

drop index if exists events_intent_idx;
drop index if exists events_session_seq_idx;
drop index if exists events_session_created_idx;

create unique index if not exists events_session_turn_uidx
  on events(session_id, turn_id);

create index if not exists events_session_event_idx
  on events(session_id, event_id);

create index if not exists events_session_created_idx
  on events(session_id, created_at);

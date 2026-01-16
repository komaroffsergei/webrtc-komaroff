-- 002_core_schema.sql
-- Best-effort compatibility adjustments, no data loss.

-- Drop old CHECK constraints on status (if any), to avoid blocking future statuses like FAILED/CANCELLED
do $$
declare
  c_name text;
begin
  select conname into c_name
  from pg_constraint
  where conrelid = 'sessions'::regclass
    and contype = 'c'
    and pg_get_constraintdef(oid) like '%status%';

  if c_name is not null then
    execute format('alter table sessions drop constraint %I', c_name);
  end if;
exception when undefined_table then
  -- sessions not present, bootstrap will create it
  null;
end $$;

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
exception when undefined_table then
  null;
end $$;

-- If old schema had seq column, remove it
do $$
begin
  if exists (
    select 1 from information_schema.columns
    where table_name='events' and column_name='seq'
  ) then
    drop index if exists events_session_seq_idx;
    alter table events drop column seq;
  end if;
exception when undefined_table then
  null;
end $$;

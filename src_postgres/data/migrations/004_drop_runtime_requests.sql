-- 004_drop_runtime_requests.sql
-- Remove legacy idempotency table no longer used by workflow runtime.

drop table if exists runtime_requests;

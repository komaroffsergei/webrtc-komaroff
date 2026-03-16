# NATS

Канонические subjects определены в `src_shared/contracts/subjects.py`.

## Основные subjects

- `nats.agent.<user_id>` — вход в `src_agent` (req-reply).
- `nats.agent.history.<user_id>` — запрос истории чата из `src_agent` (req-reply).
- `nats.events.<user_id>` — события и команды для UI (pub-sub).
- `nats.workflow.run.python` — запуск Python runtime (req-reply).
- `nats.workflow.health.python` — health Python runtime (req-reply).
- `nats.workflow.run.ruby` — запуск Ruby runtime (req-reply).
- `nats.workflow.health.ruby` — health Ruby runtime (req-reply).
- `nats.llm.<user_id>` — вызовы LLM (req-reply).
- `nats.tools.<tool_name>` — вызовы инструментов (req-reply).

## Стандарт envelope полей

Каждый межсервисный payload включает:

- `trace_id`
- `correlation_id`
- `request_id`
- `session_id`
- `ts_ms`

Это обязательная часть трассировки и идемпотентности.

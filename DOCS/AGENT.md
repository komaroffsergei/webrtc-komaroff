# src_agent

## Responsibility
`src_agent` is the orchestration bridge between HTTP ingress (`src_core`), workflow runtime (`src_langgraph`), and PostgreSQL state.
It validates inbound requests, manages session/runtime persistence, stores chat turns, and emits UI commands/events.
It does not contain scenario business logic.

## NATS API
Subscriptions:
- `nats.agent.<user_id>`: main user message requests (`AgentInboundRequest`).
- `nats.agent.history.<user_id>`: history/snapshot requests (`HistoryGetRequest`).

Outbound req/reply:
- `NATS_WORKFLOW_RUN_SUBJECT` (по умолчанию `nats.workflow.run.python`): workflow execution requests (`WorkflowRunRequest`).

Outbound events:
- `nats.events.<user_id>` via `NatsLogger` (`command/client`, `command/thought`, etc.).

## Persistence
`src_agent` uses PostgreSQL tables:
- `sessions`: session lifecycle.
- `runtime_state`: optimistic-locked workflow state + compact dialog context.
- `events`: chat history (`turn_id`, `role`, `text`, `meta`).

History API returns both:
- chat `items` from `events`,
- `runtime_context` snapshot from `runtime_state.context` (used by frontend to restore artifacts/context on shared links).

Edit flow:
- if `edit.turn_id` is provided, history tail is deleted from edited user turn onward,
- edited user turn and new assistant turn are persisted,
- runtime state is rewritten by LangGraph and saved with optimistic locking.

## Environment
Configured in `src_agent/settings.py` and `src_agent/env.example`.

- `NATS_URL`
- `NATS_AGENT_SUBJECT` (prefix)
- `NATS_AGENT_HISTORY_SUBJECT` (prefix)
- `NATS_EVENTS_SUBJECT` (prefix)
- `NATS_WORKFLOW_RUN_SUBJECT`
- для локального Docker runtime switch задается в `docker/.env`
- `WORKFLOW_TIMEOUT_SECONDS`
- `WORKFLOW_NO_RESPONDERS_RETRIES`
- `WORKFLOW_NO_RESPONDERS_RETRY_DELAY_SECONDS`
- `RUNTIME_CONFLICT_RETRIES`
- `DATABASE_URL`
- `USER_ID`

## Run/stop
Docker:
```bash
cd docker
docker compose up -d src_agent
docker compose stop src_agent
```

Local:
```bash
python -m src_agent.main
```

## Common issues
- `runtime_state version conflict`
  - Cause: concurrent updates for the same session.
  - Fix: retry is built in; if persistent, check duplicated clients writing same `session_id`.
- `no responders available` for workflow subject
  - Cause: выбранный runtime (`src_langgraph` или `src_langgraph_rb`) не запущен или `NATS_WORKFLOW_RUN_SUBJECT` указывает не на тот subject.
  - Fix: подними runtime, который обслуживает настроенный subject, и проверь `NATS_WORKFLOW_RUN_SUBJECT`.
  - Note: `src_agent` больше не переключается молча на другой subject; retries идут только в явно настроенный subject.
- `edit_turn_not_found`
  - Cause: frontend sends edit for a turn that does not exist in DB session history.
  - Fix: refresh history and retry edit from an existing user turn.

## Code pointers
- Entry: `src_agent/main.py`
- NATS server: `src_agent/service.py`
- Runner/orchestration: `src_agent/agent.py`
- Runtime persistence: `src_agent/repositories/runtime_state.py`
- DB helpers/history APIs: `src_agent/utils/db.py`

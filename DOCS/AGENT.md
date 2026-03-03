# src_agent

## Responsibility
`src_agent` is the orchestration bridge between HTTP ingress (`src_core`), workflow runtime (`src_langgraph`), and PostgreSQL state.
It validates inbound requests, manages session/runtime persistence, stores chat turns, and emits UI commands/events.
It does not contain scenario business logic.

## NATS API
Subscriptions:
- `nats.agent.<user_id>`: main user message requests (`AgentInboundRequest`).
- `nats.agent.history.<user_id>`: history requests (`HistoryGetRequest`).

Outbound req/reply:
- `nats.workflow.run`: workflow execution requests (`WorkflowRunRequest`).

Outbound events:
- `nats.events.<user_id>` via `NatsLogger` (`command/client`, `command/thought`, etc.).

## Persistence
`src_agent` uses PostgreSQL tables:
- `sessions`: session lifecycle.
- `runtime_state`: optimistic-locked workflow state + compact dialog context.
- `events`: chat history (`turn_id`, `role`, `text`, `meta`).

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
- `WORKFLOW_TIMEOUT_SECONDS`
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
  - Cause: `src_langgraph` is down or wrong `NATS_WORKFLOW_RUN_SUBJECT`.
  - Fix: start `src_langgraph` and verify subject config.
- `edit_turn_not_found`
  - Cause: frontend sends edit for a turn that does not exist in DB session history.
  - Fix: refresh history and retry edit from an existing user turn.

## Code pointers
- Entry: `src_agent/main.py`
- NATS server: `src_agent/service.py`
- Runner/orchestration: `src_agent/agent.py`
- Runtime persistence: `src_agent/repositories/runtime_state.py`
- DB helpers/history APIs: `src_agent/utils/db.py`

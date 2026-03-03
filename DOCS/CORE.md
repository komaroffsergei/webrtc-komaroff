# src_core

## Responsibility
`src_core` is the HTTP/WebRTC ingress for the browser UI.
It validates user input, forwards requests to `src_agent` over NATS, and exposes history/init endpoints for UI bootstrap.
It does not execute workflow logic.

## Endpoints
- `GET /core`: basic index endpoint.
- `POST /core/offer`: WebRTC signaling offer handling.
- `POST /core/message`: send user text to agent.
- `GET /core/history?session_id=<uuid>&limit=<n>`: restore chat history from agent storage.
- `POST /core/init_map`: fetch initial map payload for UI.

## Message flow
1. Browser calls `POST /core/message` with `{ text, session_id?, turn_id?, edit? }`.
2. `src_core` publishes transcription + voice lock events to `nats.events.<user_id>`.
3. `turn_id` is normalized to UUID before forwarding to agent.
4. `src_core` sends req/reply to `nats.agent.<user_id>`.
5. Returns `{ status: "ok", session_id }` to browser.

History flow:
1. Browser calls `GET /core/history`.
2. `src_core` sends req/reply to `nats.agent.history.<user_id>`.
3. Returns normalized history payload to browser.

## NATS subjects
- Request: `nats.agent.<user_id>`
- History request: `nats.agent.history.<user_id>`
- UI events stream: `nats.events.<user_id>`

## Environment
Configured in `src_core/settings.py` and `src_core/env.example`.

- `CORE_HOST`, `CORE_PORT`
- `NATS_URL`
- `NATS_EVENTS_SUBJECT` (prefix)
- `NATS_AGENT_SUBJECT` (prefix)
- `NATS_AGENT_HISTORY_SUBJECT` (prefix)
- `NATS_REQUEST_TIMEOUT`
- `API_URL`
- `USER_ID`

## Run/stop
Docker:
```bash
cd docker
docker compose up -d src_core
docker compose stop src_core
```

Local:
```bash
python -m src_core.main
```

## Common issues
- `address already in use` on `CORE_PORT`
  - Fix: stop Docker `src_core` container or set a free `CORE_PORT`.
- `ConnectionRefusedError` to NATS
  - Fix: start NATS (`docker compose up -d nats`) and verify `NATS_URL`.
- `session_id must be a valid UUID` for `/core/history`
  - Fix: pass the exact session UUID returned by `/core/message`.

## Code pointers
- Entry: `src_core/main.py`
- Message handler: `src_core/handlers/handle_message.py`
- Agent bridge: `src_core/handlers/handle_transcription.py`
- History handler: `src_core/handlers/handle_history.py`
- Settings: `src_core/settings.py`

# src_front

## Responsibility
`src_front` is the browser UI for chat, voice controls, and map rendering.
It sends user messages to `src_core`, subscribes to backend events over NATS WS, and renders commands/artifacts.
It does not run workflow logic.

## Session and history behavior
- Session ID is stored in `sessionStorage` under `assistant.session_id`.
- Each browser tab has its own `sessionStorage`, so each tab has an independent chat session.
- On page reload, the app restores `session_id` from `sessionStorage` and requests `GET /core/history`.
- History is rendered with stable `turn_id` values, enabling inline user message editing.

## Edit behavior
- User message edit sends `POST /core/message` with:
  - `turn_id` = edited user turn ID
  - `edit.turn_id` = same turn ID
  - existing `session_id`
- UI rewrites local history tail from edited message immediately, then waits for regenerated assistant response.

## Network flow
Outgoing:
- `POST /core/message`
- `GET /core/history`
- `POST /core/init_map`

Incoming:
- NATS WS subscription to `nats.events.<user_id>`
- Handles `command/client`, `command/thought`, status, transcription and voice lock events

## Debug logging
- Events are logged in grouped format via `src_front/src/core/logging.ts`.
- LLM debug events (`name=llm_request_debug`) and LLM responses (`name=llm_result`) are printed with structured payloads for easier inspection.
- Replay snapshot is printed as one compact expandable object on each telemetry/event tick:
  - prefix: `[dialog.replay.bundle]`
  - payload: compact object (`schema=dialog_replay@2`) without timestamp noise and trace/request ids
  - includes last 10 compact flow steps with edit context.

## Run/stop
Docker UI:
```bash
cd docker
docker compose up -d src_front
docker compose stop src_front
```

Local dev:
```bash
cd src_front
npm install
npm run dev
```

## Common issues
- No events in UI after connect
  - Fix: verify NATS WS endpoint (`/ws`) and matching `user_id` subject suffix.
- Edit returns `edit_turn_not_found`
  - Fix: session mismatch or stale UI history; reload page to restore history from backend.
- History not restored after reload
  - Fix: ensure `/core/history` is reachable and `assistant.session_id` exists in tab `sessionStorage`.

## Code pointers
- App entry and flow: `src_front/src/assistant/assistantApp.ts`
- Chat UI/edit controls: `src_front/src/ui/chatUi.ts`
- HTTP message sender: `src_front/src/core/commandHandler.ts`
- Event logging: `src_front/src/core/logging.ts`
- Agent command rendering: `src_front/src/agentCommands/*`

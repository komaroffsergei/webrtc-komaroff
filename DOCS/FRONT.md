# src_front

## Responsibility
`src_front` is the browser UI for chat, voice controls, and map rendering.
It sends user messages to `src_core`, subscribes to backend events over NATS WS, and renders commands/artifacts.
It does not run workflow logic.

## Session and history behavior
- Canonical chat route: `/chat/<session_id>`.
- URL `session_id` is the source of truth for the current dialog.
- If the app is opened without `session_id` in route, a new UUID is created and URL is replaced with `/chat/<new_session_id>`.
- `session_id` is additionally stored in `sessionStorage` under `assistant.session_id` for diagnostics/debug tools.
- On page reload or share-link open (including another PC), app restores by `session_id` via `GET /core/history`.
- Restore includes both message history and runtime artifacts snapshot (`runtime_context.artifact_memory`), including map state.

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
- Handles `command/client`, `command/thought`, status, transcription, `transcription_pending`, and voice lock events

Voice UX interim state:
- After local VAD detects end of user speech, chat shows centered flash `Транскрипция...`.
- Flash is also supported via server event `command/transcription_pending` (if ASR publishes pending markers).
- Flash hides when final `command/transcription` arrives, on `voice.blocked=false`, on reconnect/disconnect reset, or when speech resumes.

Resilience:
- `/core/message` has client-side timeout (default `70000ms`, configurable via `window.SETTINGS.MESSAGE_REQUEST_TIMEOUT_MS`).
- NATS reconnect uses exponential backoff (1s..15s).
- `Stale Connection` errors force connection reset before retry to avoid fake reconnect loops.

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
- `NatsError: 'Stale Connection'` repeats but events never return
  - Fix: ensure frontend version includes forced reset logic from `src_front/src/net/natsClient.ts` and retry backoff in `AssistantApp`.
- Edit returns `edit_turn_not_found`
  - Fix: session mismatch or stale UI history; reload page to restore history from backend.
- History not restored after reload
  - Fix: ensure `/core/history` is reachable and route has valid `/chat/<uuid>`.

## Code pointers
- App entry and flow: `src_front/src/assistant/assistantApp.ts`
- Chat UI/edit controls: `src_front/src/ui/chatUi.ts`
- HTTP message sender: `src_front/src/core/commandHandler.ts`
- Event logging: `src_front/src/core/logging.ts`
- Agent command rendering: `src_front/src/agentCommands/*`

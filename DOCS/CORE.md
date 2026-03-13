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
2. `src_core` normalizes `turn_id` to UUID before forwarding to agent.
3. `src_core` sends req/reply to `nats.agent.<user_id>`.
4. Returns:
   - success: `{ status: "ok", session_id }`
   - downstream error: `{ status: "error", session_id, error, details? }` with HTTP 502/504

## Live ASR flow from `/chat`
1. Browser sends a WebRTC audio track to `POST /core/offer`.
2. `handle_track.py` builds `TrackSourceNode -> WhisperStreamNode`.
3. `TrackSourceNode` normalizes audio to mono `16kHz` packed `s16`.
4. `WhisperStreamNode` publishes binary wire packets to `inference.whisper.stream.<session_id>`.
5. `stt_whisper_to_nats` does server-side utterance segmentation and talks to `linto_stt_whisper` over websocket.
6. `src_core` receives stage/final payloads from `inference.whisper.text.<session_id>`.
7. `handle_transcription.py` publishes:
   - `command/transcription_state` for `speech_started`, `transcribing`, `thinking`, `idle`, `error`
   - `command/voice` to block/unblock mic and text input
   - `command/transcription` once final text is ready
8. Only final text is forwarded to `src_agent`; partial/stage payloads stay in UI/event flow.

History flow:
1. Browser calls `GET /core/history`.
2. `src_core` sends req/reply to `nats.agent.history.<user_id>`.
3. Returns normalized payload to browser:
   - `items` (chat turns)
   - `runtime_context` (snapshot of workflow context/artifacts for full UI restore)

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
- `/core/message` returns 502/504
  - Cause: agent/workflow timeout or temporary unavailability.
  - Fix: check `src_agent` and `src_langgraph` logs, and tune `NATS_REQUEST_TIMEOUT`/`WORKFLOW_TIMEOUT_SECONDS`.
- `session_id must be a valid UUID` for `/core/history`
  - Fix: pass the exact session UUID returned by `/core/message`.

## Code pointers
- Entry: `src_core/main.py`
- Message handler: `src_core/handlers/handle_message.py`
- Agent bridge: `src_core/handlers/handle_transcription.py`
- History handler: `src_core/handlers/handle_history.py`
- Settings: `src_core/settings.py`

# webrtc-komaroff-dev

Local development guide for the WebRTC + NATS microservices stack.

## Components

- `src_core` - WebRTC signaling + audio pipeline (publishes ASR requests to NATS).
- `src_agent` - thin runner (NATS + PostgreSQL): stores `runtime_state`, calls n8n over NATS, publishes UI events.
- `src_n8n` - NATS bridge: `nats.n8n.run` -> n8n webhook, plus an internal HTTP tool proxy for workflows.
- `n8n` - workflow orchestration (stores workflows in Postgres schema `n8n`).
- `src_llm` - LLM gateway over NATS (strict JSON schemas; can run in mock mode).
- `src_api_gateway` - mock APIs + NATS tools (`nats.tools.*`) used by workflows via `src_n8n` tool proxy.
- `src_front` - web UI (connects to NATS over WebSocket).
- Infrastructure (Docker): NATS, PostgreSQL, Redis (for n8n queue mode).

ASR/Whisper is expected to run as an external service (see "Whisper / ASR service").

## Prerequisites

- Docker + Docker Compose v2
- Python 3.12+ (for running services directly)
- Node.js (only for `src_front` in dev mode)

## Start with Docker (recommended)

This repo provides NATS + PostgreSQL for local multi-repo mode (`webrtc-komaroff-dev` + `voice-chat/n8n`).

Start infra (NATS + PostgreSQL):

```bash
docker compose -f docker/docker-compose.yml up -d nats src_postgres
```

Start the full stack (builds and starts all services defined in compose):

```bash
docker compose -f docker/docker-compose.yml up -d
```

### How to use (quick start)

1) Open the frontend at `http://127.0.0.1:8080/` and send a message.
2) The UI sends text to `src_agent` via NATS. `src_agent` persists runtime in Postgres and calls `src_n8n` over NATS.
3) `src_n8n` triggers the selected n8n workflow and returns a structured response that is rendered by the UI.

Useful endpoints (host machine):

- NATS TCP: `nats://127.0.0.1:14222`
- NATS WebSocket: `ws://127.0.0.1:9222`
- NATS WebSocket (via Front reverse-proxy): `ws://127.0.0.1:8080/ws`
- PostgreSQL: `127.0.0.1:5432` (user: `mcp`, password: `mcp_pass`, db: `mcp`)
- Core: `http://127.0.0.1:8000/core`
- API Gateway: `http://127.0.0.1:8101/api`
- Front: `http://127.0.0.1:8080/`
- n8n UI/API: `http://127.0.0.1:5679/`
- n8n Webhooks (для локального `src_n8n`): `http://127.0.0.1:5679/webhook`

Notes:

- n8n runtime is moved to `~/dev/monitorsoft/voice-chat/n8n`.
- This repo publishes host ports required by that stack: NATS `14222`, Postgres `5432`.

## Documentation

Service-level docs live under `DOCS/`:

- `DOCS/START_HERE.md`
- `DOCS/FRONT.md`
- `DOCS/CORE.md`
- `DOCS/AGENT.md`
- `DOCS/N8N.md`
- `DOCS/N8N_BRIDGE.md`
- `DOCS/LLM.md`
- `DOCS/API_GATEWAY.md`
- `DOCS/POSTGRES.md`
- `DOCS/NATS.md`
- `DOCS/E2E.md`

## Run services directly (no Docker for apps)

You can keep infra in Docker, but run Python services from your IDE/terminal.

### 1) Start infra

```bash
docker compose -f docker/docker-compose.yml up -d nats src_postgres
```

Sanity checks:

```bash
nc -zvw2 127.0.0.1 14222
nc -zvw2 127.0.0.1 5432
```

### 2) Python environment

From `webrtc-komaroff-dev/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_core/requirements.txt -r src_agent/requirements.txt -r src_n8n/requirements.txt -r src_llm/requirements.txt -r src_api_gateway/requirements.txt
```

### 3) Configure `.env` files (optional)

Each service reads environment variables from its own `.env` file:

- `src_core/env.example`
- `src_agent/env.example`
- `src_llm/env.example`
- `src_api_gateway/.env.example`

Minimum values for local run:

- `NATS_URL=nats://127.0.0.1:14222`
- `DATABASE_URL=postgresql://mcp:mcp_pass@127.0.0.1:5432/mcp` (for `src_agent`)

### 4) Run services

From `webrtc-komaroff-dev/`:

```bash
# API Gateway (script, not a package)
python src_api_gateway/main.py
```

In other terminals:

```bash
python -m src_core.main
python -m src_agent.main
python -m src_llm.main
```

If docker-compose is running, `src_core` inside Docker already binds `0.0.0.0:8000`. To run `src_core` locally:

- stop the container `webrtc-komaroff-dev-src_core-1`, or
- set `CORE_PORT` to a free port (example: `CORE_PORT=8002`).

### Frontend (dev mode)

From `webrtc-komaroff-dev/src_front/`:

```bash
npm install
npm run dev
```

By default, dev mode expects NATS WebSocket on `ws://localhost:9222`.

### Run `src_n8n` locally (IDE) while n8n stays in Docker

This repo assumes `n8n`, `n8n_webhook`, `n8n_worker`, and `src_n8n` are all started via Docker Compose.
`TOOL_PROXY_URL` is fixed inside the Docker network as `http://src_n8n:9000/tool` to avoid host-specific routing.

## Whisper / ASR service (external)

`src_core` publishes audio packets to NATS subjects:

- input: `nats.asr.input.<token>`
- output: `nats.asr.output.<token>`

Any ASR service that subscribes to `nats.asr.input.>` and replies to the matching output subject will work.

Recommended implementation: `voice-chat/py_faster_whisper` (separate repo).

### Run ASR in Docker (recommended)

1) Start NATS from this repo:

```bash
cd webrtc-komaroff-dev/docker
docker compose up -d nats
```

2) Start ASR service from the other repo (it attaches to the same `monitorsoft_nats` network):

```bash
cd ../../voice-chat/py_faster_whisper/docker
docker compose up -d --build
```

Defaults:

- ASR container uses `NATS_URL=ws://nats:9222` (service DNS `nats` is provided by the shared network).
- WebUI: `http://127.0.0.1:8090/`

## n8n Orchestration Over NATS

### n8n Web UI

Open n8n in the browser:

- Web UI: `http://127.0.0.1:5679/`

On first start n8n may ask you to create an owner account.

The demo workflows are named and versioned as:

- `router@1.0.0`
- `echo@1.0.0`
- `collect_name@1.0.0`
- `airports_and_weather@1.0.0`

Important: this repo bootstraps workflows from `docker/n8n/workflows/*.json`. If you change workflows in the UI,
export them back to JSON (and commit) or disable the bootstrap import, otherwise your local changes can be overwritten
on the next stack recreate.

### NATS subjects

Canonical subjects are defined in `src_shared/contracts/subjects.py`.

- `nats.agent.<user_id>`: inbound user text to `src_agent` (req-reply).
- `nats.events.<user_id>`: UI events/commands to `src_front` (pub-sub).
- `nats.n8n.run`: `src_agent` -> `src_n8n` (req-reply).
- `nats.n8n.health`: health check for `src_n8n` (req-reply).
- `nats.llm.<user_id>`: LLM gateway (`src_llm`) (req-reply).
- `nats.tools.<name>`: tool calls via NATS (`src_api_gateway` provides demo tools).

### Message contracts

Pydantic v2 models live under `src_shared/contracts/` and are validated on every service boundary.

Cross-service envelopes always include:

- `trace_id` (uuid)
- `correlation_id` (uuid, optional; defaults to `trace_id`)
- `request_id` (uuid; used for idempotency)
- `session_id` (uuid; required for stateful runs)
- `ts_ms` (unix timestamp in milliseconds)

Key models:

- `AgentInboundRequest` / `AgentInboundResponse`
- `N8nRunRequest` / `N8nRunResponse`
- `ToolCallRequest` / `ToolCallResponse`
- `LlmRequest` / `LlmResponse`

### Runtime state (user-in-the-loop)

`src_agent` persists per-session runtime under the Postgres `runtime_state` table:

- `active_workflow_id`: when set, the next user message continues that workflow.
- `pending`: when set, UI prompts the user for a missing field (e.g. radius).
- `version`: optimistic locking. If concurrent updates happen, `src_agent` reloads runtime and retries the n8n run.

### Idempotency

`src_n8n` stores `nats.n8n.run` results in Postgres table `runtime_requests` and returns the cached response for
duplicate `request_id` values.

### Workflows

Workflows are stored and visually managed in n8n, but this repo bootstraps demo workflows from JSON files:

- `docker/n8n/workflows/router_1_0_0.json`
- `docker/n8n/workflows/echo_1_0_0.json`
- `docker/n8n/workflows/collect_name_1_0_0.json`
- `docker/n8n/workflows/airports_and_weather_1_0_0.json`

To add a new workflow:

1) Create/export the workflow JSON into `docker/n8n/workflows/`.
2) Give it a stable runtime id in the workflow name (example: `my_flow@1.0.0`).
3) Add it to `src_n8n/settings.py` mappings so `src_n8n` can call the correct n8n webhook path.
4) Ensure the workflow returns a JSON object compatible with `N8nRunResponse`.

### Run E2E tests

E2E tests are a small dockerized runner that talks to the stack over NATS and validates the 3 demo workflows:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

### Run ASR directly (no Docker)

From `voice-chat/py_faster_whisper/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src/requirements.txt

export NATS_URL=ws://127.0.0.1:9222
python -m src.main
```

## Legacy `src_whisper` (in this repo)

This repo historically contained a Python ASR implementation under `src_whisper/`.
It is not used by default:

- `webrtc-komaroff-dev/docker/docker-compose.yml` does not start it (it is behind the `legacy_whisper` profile).
- Other services do not import `src_whisper` (only communicate via NATS subjects).

If you want to remove it from the repo, delete `src_whisper/` and also remove/clean up:

- `webrtc-komaroff-dev/docker/whisper/`
- `webrtc-komaroff-dev/stack/webrtc.drs` (if your branch still deploys `src_whisper`)

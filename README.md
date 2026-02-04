# webrtc-komaroff-dev

Local development guide for the WebRTC + NATS microservices stack.

## Components

- `src_core` - WebRTC signaling + audio pipeline (publishes ASR requests to NATS).
- `src_agent` - agent backend (uses NATS + PostgreSQL).
- `src_llm` - LLM service (uses NATS).
- `src_api_gateway` - mock HTTP API used by the agent.
- `src_front` - web UI (connects to NATS over WebSocket).
- Infrastructure (Docker): NATS and PostgreSQL.

ASR/Whisper is expected to run as an external service (see "Whisper / ASR service").

## Prerequisites

- Docker + Docker Compose v2
- Python 3.12+ (for running services directly)
- Node.js (only for `src_front` in dev mode)

## Start with Docker (recommended)

This repo uses one shared Docker network (`monitorsoft_nats`) so you can run the ASR service from another repo
while still using the same NATS instance.

Create the shared network once (ignore the error if it already exists):

```bash
docker network create monitorsoft_nats
```

Start infra (NATS + PostgreSQL):

```bash
docker compose -f docker/docker-compose.yml up -d nats src_postgres
```

Start the full stack (builds and starts all services defined in compose):

```bash
docker compose -f docker/docker-compose.yml up -d
```

Useful endpoints (host machine):

- NATS TCP: `nats://127.0.0.1:4222`
- NATS WebSocket: `ws://127.0.0.1:9222`
- NATS WebSocket (via Front reverse-proxy): `ws://127.0.0.1:8080/ws`
- PostgreSQL: `127.0.0.1:5432` (user: `mcp`, password: `mcp_pass`, db: `mcp`)
- Core: `http://127.0.0.1:8000/core`
- API Gateway: `http://127.0.0.1:8100/api`
- Front: `http://127.0.0.1:8080/`

Notes:

- NATS and PostgreSQL are bound to `127.0.0.1` on purpose (local-only).
- Compose project name is pinned, so running other repos from their own `docker/` folders does not collide.

## Run services directly (no Docker for apps)

You can keep infra in Docker, but run Python services from your IDE/terminal.

### 1) Start infra

```bash
docker compose -f docker/docker-compose.yml -d nats src_postgres
```

Sanity checks:

```bash
nc -zvw2 127.0.0.1 4222
nc -zvw2 127.0.0.1 5432
```

### 2) Python environment

From `webrtc-komaroff-dev/`:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_core/requirements.txt -r src_agent/requirements.txt -r src_llm/requirements.txt -r src_api_gateway/requirements.txt
```

### 3) Configure `.env` files (optional)

Each service reads environment variables from its own `.env` file:

- `src_core/env.example`
- `src_agent/env.example`
- `src_llm/env.example`
- `src_api_gateway/.env.example`

Minimum values for local run:

- `NATS_URL=nats://127.0.0.1:4222`
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

### Frontend (dev mode)

From `webrtc-komaroff-dev/src_front/`:

```bash
npm install
npm run dev
```

By default, dev mode expects NATS WebSocket on `ws://localhost:9222`.

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

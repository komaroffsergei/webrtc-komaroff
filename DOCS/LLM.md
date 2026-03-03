# src_llm

## Responsibility
`src_llm` is a NATS request/reply gateway to the underlying language model (local or remote).
It validates `LlmRequest`, runs mode-specific inference, and returns strict `LlmResponse` payloads.
It does not own session persistence.

## NATS subjects
- Inbound requests: `nats.llm.<user_id>`
- Outbound events/logs: `nats.events.<user_id>`

## Supported modes
Defined in `src_shared/contracts/llm.py`:
- `routing_decision`
- `params_extract`
- `revise`
- `tool_decision`
- `tool_params`
- `final_response`

## Debug output
For every inbound LLM request, `src_llm` emits:
- `log/info name=llm_runtime_config` with startup runtime config (`mode`, `configured_model`, `llm_context_size`)
- `log/info name=llm_request_debug` with trace, mode, requested/configured model, constraints, and truncated input payload
- `log/info name=llm_result` with response payload and `_debug` block (`effective_model`, `provider`, `duration_ms`)

This is consumed by frontend console logging for readable per-request diagnostics.

## Environment
Configured in `src_llm/settings.py` and `src_llm/env.example`.

- `NATS_URL`
- `NATS_LLM_SUBJECT` (prefix)
- `NATS_EVENTS_SUBJECT` (prefix)
- `USER_ID`
- `LLM_MODE=local|remote`
- `OLLAMA_URL` (for `nats2ollama` use `https://nats2ollama.gis-master.ru`)
- `LLM_LOCAL_MODEL`
- `LLM_REMOTE_MODEL`
- `DEFAULT_MAX_TOKENS`
- `LLM_CONTEXT_SIZE`

NATS2Ollama endpoint mode:
- Service uses plain endpoint access (no auth headers/tokens/cookies).
- Base URL must not include `/api/chat` path because Ollama client calls `/api/*` relative to `OLLAMA_URL`.

## Run/stop
Docker:
```bash
cd docker
docker compose up -d src_llm
docker compose stop src_llm
```

Local:
```bash
python -m src_llm.main
```

## Common issues
- `LLM_MODE must be either 'local' or 'remote'`
  - Fix: set `LLM_MODE` to `local` or `remote`.
- `Model did not return a JSON object`
  - Cause: model ignored JSON-only instruction.
  - Fix: check `llm_request_debug` and model config/temperature.
- `405 Method Not Allowed` from remote model call
  - Cause: wrong base URL (using `/api/chat` as host path).
  - Fix: set `OLLAMA_URL=https://nats2ollama.gis-master.ru`.
- No response on NATS request
  - Cause: service not subscribed to `nats.llm.<user_id>`.
  - Fix: verify `USER_ID` and subject prefix configuration.

## Code pointers
- Entry: `src_llm/main.py`
- Core logic: `src_llm/service.py`
- NATS wrapper: `src_llm/utils/base_service.py`
- Event logger: `src_llm/utils/nats_logger.py`
- Contracts: `src_shared/contracts/llm.py`

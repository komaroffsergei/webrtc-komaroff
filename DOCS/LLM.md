# src_llm

`src_llm` — единый gateway к модели по NATS.

## Subject

- `nats.llm.<user_id>` (req-reply)

## Поддерживаемые режимы

- `routing_decision`
- `tool_params`
- `final_response`
- дополнительные режимы из `src_shared/contracts/llm.py` при необходимости

## Конфиг

- `LLM_MODE=local|remote`
- `OLLAMA_URL`
- `LLM_LOCAL_MODEL`
- `LLM_REMOTE_MODEL`

## Поток вызова

`src_langgraph` -> `nats.llm.<user_id>` -> `src_llm` -> модель -> `LlmResponse`.

## Где смотреть код

- `src_llm/service.py`
- `src_llm/settings.py`
- `src_shared/contracts/llm.py`

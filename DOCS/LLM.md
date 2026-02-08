# src_llm (LLM gateway по NATS)

## Что это

`src_llm` предоставляет один NATS req-reply endpoint для структурированных вызовов LLM.

Subject:

- `nats.llm.<user_id>`

Режимы (строгие схемы):

- `routing_decision`
- `params_extract`
- `revise`

Схемы request/response валидируются Pydantic моделями из `src_shared/contracts`.

## Кто вызывает

В текущей архитектуре LLM вызывается из workflows n8n через tool proxy:

- n8n HTTP Request node -> `src_n8n /tool` -> NATS `nats.llm.<user_id>`

## Mock mode

В docker-compose используется `LLM_MODE=mock`, чтобы демо-сценарии работали детерминированно.

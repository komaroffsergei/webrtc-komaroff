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

## LLM mode

Поддерживаются только два режима:

- `LLM_MODE=local`
- `LLM_MODE=remote`

## Код (куда смотреть)

- NATS сервис + парсинг/валидация: `src_llm/service.py`
- Базовый NATS service helper: `src_llm/utils/base_service.py`
- Контракты режимов: `src_shared/contracts/*`

## Частые ошибки

### `llm_failed: Extra data ...` / модель вернула невалидный JSON

Причина: модель ответила не одним JSON-объектом (например, добавила пояснение текстом) или вернула несколько JSON подряд.

Что делать:

- используйте `LLM_MODE=local` или `LLM_MODE=remote`
- проверьте, что prompts требуют **строго один JSON объект** и что включён строгий парсер

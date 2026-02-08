# src_api_gateway (HTTP API + NATS tools)

## Что это

`src_api_gateway` предоставляет:

- HTTP endpoints под `/api/*` (используется `src_core` для bootstrap данных UI)
- NATS tools под `nats.tools.*` (используется workflows n8n через `src_n8n` tool proxy)

## Демо-tools (NATS)

Subjects:

- `nats.tools.search_airports_nearby` (req-reply)
- `nats.tools.get_weather` (req-reply)

Оба tools принимают `ToolCallRequest` и возвращают `ToolCallResponse`.

Идемпотентность:

- artifact keys детерминированы: `<tool_name>:<request_id>`

## Демо HTTP endpoints

Примеры:

- `GET /api/airports/list`
- `GET /api/pilot/location`

Это mock endpoints для разработки и демо.

## Код (куда смотреть)

- HTTP API: `src_api_gateway/main.py`
- NATS tools: `src_api_gateway/tools/*` (или см. роутинг subjects в `main.py`)
- Контракты: `src_shared/contracts/*`

## Частые ошибки

### Tool не найден (`tool_not_found`) или таймаут по NATS

Причины:

- неправильный subject (ожидается `nats.tools.<name>`)
- не запущен `src_api_gateway` или NATS

Проверка:

- `docker compose -f docker/docker-compose.yml ps src_api_gateway nats`

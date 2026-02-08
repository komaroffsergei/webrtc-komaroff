# NATS (обмен сообщениями)

## Правила транспорта в этом репо

Весь межсервисный обмен идёт через NATS:

- req-reply для синхронных вызовов
- pub-sub для UI событий

HTTP разрешён только внутри docker-сети между `src_n8n` и `n8n` (включая tool proxy из workflows n8n в `src_n8n`).

## Канонические subjects

Смотрите `src_shared/contracts/subjects.py`.

- `nats.agent.<user_id>`: UI/core -> agent (req-reply)
- `nats.events.<user_id>`: backend -> UI (pub-sub)
- `nats.n8n.run`: agent -> n8n bridge (req-reply)
- `nats.n8n.health`: healthcheck для bridge (req-reply)
- `nats.llm.<user_id>`: LLM gateway (req-reply)
- `nats.tools.<name>`: tools (req-reply)

## Trace поля

Каждый межсервисный payload включает:

- `trace_id` (uuid)
- `correlation_id` (uuid; по умолчанию = trace_id)
- `request_id` (uuid; ключ идемпотентности)
- `session_id` (uuid)
- `ts_ms` (unix timestamp в миллисекундах)

## Частые ошибки

### `ConnectionRefusedError ... :4222`

Причина: NATS не запущен или недоступен на `127.0.0.1:4222`.

Что делать:

- `docker compose -f docker/docker-compose.yml up -d nats`

### UI не подключается к NATS WebSocket

Причина: не проброшен порт `9222` или выбран неправильный URL.

Проверка:

- `docker compose -f docker/docker-compose.yml ps nats`
- UI должен подключаться к `ws://127.0.0.1:9222` (dev) или через прокси (docker/nginx)

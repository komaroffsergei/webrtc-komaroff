# src_agent (тонкий раннер)

## Что это

`src_agent` — тонкий раннер без логики сценариев:

- Принимает текст пользователя по NATS (`nats.agent.<user_id>`, req-reply).
- Гарантирует наличие строки в `sessions` (Postgres).
- Загружает `runtime_state` (на сессию) из Postgres.
- Вызывает n8n через мост `src_n8n` по NATS (`nats.n8n.run`, req-reply).
- Сохраняет `next_runtime` обратно в Postgres с optimistic locking (`runtime_state.version`).
- Публикует UI-команды/события в `nats.events.<user_id>` (pub-sub).

## Входящий запрос

Subject: `nats.agent.<user_id>`

Payload: `AgentInboundRequest` (см. `src_shared/contracts`):

- `trace_id`, `correlation_id`, `request_id`, `session_id`, `ts_ms`
- `text`
- опционально `edit`

## Запрос в n8n (через мост)

Subject: `nats.n8n.run`

Payload: `N8nRunRequest`:

- `session_id`, `text`, `edit`
- `runtime` (загружен из Postgres)
- trace fields

## Ошибки и отсутствие fallback

Fallback "чатикам" отсутствует. Если router не выбрал workflow или workflow упал, UI получает явную ошибку
(`SHOW_ERROR_MESSAGE`), а ответ на req-reply будет `status=FAILED`.

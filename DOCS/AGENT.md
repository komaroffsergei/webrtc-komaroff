# src_agent

`src_agent` — тонкий раннер без сценарной логики.

## Что делает

1. Принимает `AgentInboundRequest` по `nats.agent.<user_id>`.
2. Загружает `runtime_state` из Postgres.
3. Отправляет `WorkflowRunRequest` в `nats.workflow.run`.
4. Сохраняет `next_runtime` обратно в `runtime_state` (optimistic lock).
5. Публикует команды UI в `nats.events.<user_id>`.

## Зачем trace-поля

- `trace_id` — единая сквозная трасса запроса между сервисами.
- `correlation_id` — связывает дочерние/параллельные вызовы внутри одной операции.
- `request_id` — идемпотентность конкретного запроса.
- `session_id` — состояние диалога пользователя между сообщениями.

Без этих полей сложно диагностировать гонки, дубли и таймауты в распределенной цепочке.

## Где смотреть код

- `src_agent/service.py`
- `src_agent/agent.py`
- `src_agent/repositories/runtime_state.py`
- `src_shared/contracts/agent.py`
- `src_shared/contracts/workflow.py`

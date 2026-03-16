# E2E проверки

В репозитории есть небольшой dockerized E2E runner, который проверяет сценарии через NATS.

Запуск:

```bash
cd docker
docker compose --profile test run --rm --build src_e2e
```

Локальный Docker по умолчанию уже направлен на Ruby runtime через `docker/.env`. Разовый запуск с явным override:

```bash
cd docker
COMPOSE_PROFILES=langgraph_rb \
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.ruby \
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.ruby \
docker compose --profile test run --rm --build src_e2e
```

Python runtime:

```bash
cd docker
COMPOSE_PROFILES=langgraph \
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.python \
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.python \
docker compose --profile test run --rm --build src_e2e
```

Что проверяется:

- LLM debug stream содержит `configured_model` в `llm_request_debug` для реального запроса
- `free_speech`: DONE + SHOW_MESSAGE
- `where_my_flight`: DONE + SHOW_MESSAGE (по запросу с номером рейса)
- `find_nearest_airport`: DONE + map events (`SET_POSITION`, `SET_AIRPORTS`, `BUILD_ROUTE`)
- `free_speech` follow-up после инструментального контекста:
  - не должен отвечать шаблоном "нет данных в текущем контексте" для факт-вопроса
  - должен использовать контекст сущностей и выдавать содержательный факт-ответ
- `edit`-ветка:
  - после редактирования исходного user-turn история ветвится заново
  - факт-вопрос в новой ветке не должен деградировать в "нет данных в контексте"
  - ответ должен использовать знания модели и содержать конкретный факт (например, год)

Дополнительно:

- `echo` проверяется только в Python runtime (`nats.workflow.health.python`), потому что Ruby runtime его не реализует.
- Выбор runtime для e2e делается только через workflow subjects: `NATS_WORKFLOW_RUN_SUBJECT` у `src_agent` и `NATS_WORKFLOW_HEALTH_SUBJECT` у `src_e2e`.

# E2E проверки

В репозитории есть небольшой dockerized E2E runner, который проверяет сценарии через NATS.

Запуск:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

Что проверяется:

- LLM debug stream содержит `configured_model` в `llm_request_debug` для реального запроса
- `echo`: DONE + SHOW_MESSAGE
- `free_speech`: DONE + SHOW_MESSAGE
- `where_my_flight`: DONE + SHOW_MESSAGE (по запросу с номером рейса)
- `find_nearest_airport`: DONE + map events (`SET_POSITION`, `SET_AIRPORTS`, `BUILD_ROUTE`)
- `free_speech` follow-up после инструментального контекста:
  - не должен отвечать шаблоном "нет данных в текущем контексте" для факт-вопроса
  - должен использовать контекст сущностей и выдавать содержательный факт-ответ

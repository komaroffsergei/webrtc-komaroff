# E2E проверки

В репозитории есть небольшой dockerized E2E runner, который проверяет сценарии через NATS.

Запуск:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

Что проверяется:

- `echo`: DONE + SHOW_MESSAGE
- `free_speech`: DONE + SHOW_MESSAGE
- `where_my_flight`: DONE + SHOW_MESSAGE (по запросу с номером рейса)
- `find_nearest_airport`: DONE + map events (`SET_POSITION`, `SET_AIRPORTS`, `BUILD_ROUTE`)

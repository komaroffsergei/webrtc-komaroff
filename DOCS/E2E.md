# E2E проверки

В репозитории есть небольшой dockerized E2E runner, который проверяет демо-workflows через NATS.

Запуск:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

Что проверяется:

- `echo@1.0.0`: DONE + SHOW_MESSAGE
- `collect_name@1.0.0`: RUNNING -> DONE (user-in-the-loop)
- `airports_and_weather@1.0.0`: RUNNING -> DONE + SHOW_AIRPORTS
- идемпотентность по `request_id`: повторный запрос возвращает тот же ответ и статус в `runtime_requests`

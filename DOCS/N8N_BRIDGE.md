# src_n8n (мост NATS <-> n8n)

## Что это

`src_n8n` — единственный сервис, который ходит в n8n по HTTP.

Он предоставляет:

- NATS bridge (req-reply):
  - subject: `nats.n8n.run`
  - валидирует запросы (`N8nRunRequest`)
  - вызывает нужный n8n webhook и валидирует ответ (`N8nRunResponse`)
- Tool proxy endpoint для workflows n8n:
  - HTTP: `POST http://src_n8n:9000/tool`
  - n8n использует HTTP Request node, чтобы вызвать tool по имени
  - `src_n8n` форвардит tool-вызовы в NATS (`nats.tools.<name>` или `nats.llm.<user_id>`)

## Идемпотентность

Для `nats.n8n.run` идемпотентность обеспечивается кэшем ответа `N8nRunResponse` в Postgres таблице `runtime_requests`
по ключу `request_id`. Повторный `request_id` возвращает сохранённый ответ.

## Устойчивость webhook routing

Импорт workflows в n8n может очистить таблицу `n8n.webhook_entity`. `src_n8n` восстанавливает нужные webhook routes
на старте и также повторяет запрос один раз при HTTP 404 от n8n, предварительно пересоздав `webhook_entity` строки.

## Маппинг workflows

`src_n8n/settings.py` мапит runtime workflow ids (например, `echo@1.0.0`) к стабильным n8n workflow ids и webhook paths.

Формат webhook URL в этом репо:

- `<N8N_WEBHOOK_BASE_URL>/<workflowId>/webhook/<path>`

Пример:

- `http://n8n_webhook:5678/webhook/Router1o0o0o0Abc/webhook/router_1_0_0`

## Режимы запуска: Docker vs локально (IDE)

Важно: **не запускайте одновременно два экземпляра `src_n8n`** (контейнер + локальный процесс).
Иначе запросы будут “делиться” между ними (NATS queue group), и поведение будет непредсказуемым.

### Вариант 1 (рекомендуемый): всё в Docker

- Запуск: `docker compose -f docker/docker-compose.yml up -d --build`
- Остановка только моста: `docker compose -f docker/docker-compose.yml stop src_n8n`

В контейнере `src_n8n` использует:

- `N8N_WEBHOOK_BASE_URL=http://n8n_webhook:5678/webhook`
- tool proxy вызывается из n8n по `TOOL_PROXY_URL` (по умолчанию `http://src_n8n:9000/tool`)

### Вариант 2: `src_n8n` локально (для отладки), остальное в Docker

1) Остановите контейнер моста:

- `docker compose -f docker/docker-compose.yml stop src_n8n`

Проверка (должен быть `Exited` или отсутствовать в списке):

- `docker compose -f docker/docker-compose.yml ps src_n8n`

2) Поднимите нужную инфраструктуру (если ещё не поднята):

- `docker compose -f docker/docker-compose.yml up -d nats src_postgres redis n8n n8n_webhook n8n_worker src_llm src_api_gateway src_agent src_front`

3) Запустите `src_n8n` локально с корректными env:

- `NATS_URL=nats://127.0.0.1:4222`
- `DATABASE_URL=postgresql://mcp:mcp_pass@127.0.0.1:5432/mcp`
- `N8N_WEBHOOK_BASE_URL=http://127.0.0.1:5679/webhook`

Запуск:

- `python -m src_n8n.main`

4) Чтобы n8n (в контейнере) мог вызвать tool proxy на хосте, используется переменная `TOOL_PROXY_URL`.
В `docker/docker-compose.yml` по умолчанию стоит `http://src_n8n:9000/tool`, но для локального `src_n8n` переключите на:

- `TOOL_PROXY_URL=http://host.docker.internal:9000/tool`

`host.docker.internal` уже добавлен в `extra_hosts` для n8n-сервисов.
Также в compose включено `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, чтобы разрешить `$env.TOOL_PROXY_URL` в expressions.

Важно: **переменные окружения читаются при старте контейнера**. Если `n8n` уже запущен, одного `docker compose exec ...` недостаточно — нужно пересоздать `n8n*` контейнеры.

Пример команды (пересоздаёт n8n процессы с новой переменной окружения):

- `TOOL_PROXY_URL=http://host.docker.internal:9000/tool docker compose -f docker/docker-compose.yml up -d --force-recreate n8n n8n_webhook n8n_worker`

Альтернатива (удобнее): используйте готовый compose override:

- `docker compose -f docker/docker-compose.yml -f docker/docker-compose.local-src_n8n.yml up -d --force-recreate n8n n8n_webhook n8n_worker`

Проверка, что переменная применилась (должно быть `http://host.docker.internal:9000/tool`):

- `docker compose -f docker/docker-compose.yml exec -T n8n sh -lc 'echo $TOOL_PROXY_URL'`
- `docker compose -f docker/docker-compose.yml exec -T n8n_worker sh -lc 'echo $TOOL_PROXY_URL'`

## Код (куда смотреть)

- NATS bridge + tool proxy: `src_n8n/service.py`
- Конфигурация: `src_n8n/settings.py`
- Контракты запросов/ответов: `src_shared/contracts/*`

## Частые ошибки

### `Failed to call n8n webhook` (не подключается)

Причины:

- неверный `N8N_WEBHOOK_BASE_URL` (для Docker и для локального запуска он разный)
- `n8n_webhook` не запущен

Проверка:

- UI: `http://127.0.0.1:5679/`
- контейнеры: `docker compose -f docker/docker-compose.yml ps n8n n8n_webhook n8n_worker`

### `n8n returned 500 ... Hint: n8n must be able to reach the tool proxy URL`

Причина: workflow в n8n пытается вызвать tool proxy по URL, который не достижим из контейнера.

Самый частый случай:

- `src_n8n` запущен локально, а в n8n осталось `TOOL_PROXY_URL=http://src_n8n:9000/tool`

Решение:

- применить override `docker/docker-compose.local-src_n8n.yml` и пересоздать `n8n*` контейнеры (см. выше)

### `ExpressionError: Access to env vars denied` (в n8n)

Причина: в workflow используется `{{$env.TOOL_PROXY_URL}}`, но n8n запрещает доступ к env в expressions.

Решение (уже включено в compose этого репо):

- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`

Если меняли compose/окружение — проверьте env в контейнере:

- `docker compose -f docker/docker-compose.yml exec -T n8n sh -lc 'echo $N8N_BLOCK_ENV_ACCESS_IN_NODE'`

### Дубли/нестабильность при отладке

Причина: одновременно запущены два экземпляра `src_n8n` (контейнер + локальный).

Решение:

- оставить только один инстанс (для локального режима — `docker compose ... stop src_n8n`)

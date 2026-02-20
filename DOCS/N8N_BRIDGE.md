# src_n8n (мост NATS <-> n8n)

> NOTE: Документ частично устарел. После миграции bridge вызывает только `router_1_0_0` и не использует `WORKFLOW_WEBHOOK_PATHS`/`webhook_entity`-восстановление.
> Актуальный source-of-truth: `~/dev/monitorsoft/voice-chat/n8n/src/service.py` и `~/dev/monitorsoft/voice-chat/n8n/src/settings.py`.

## Где находится код bridge

Код и сборка `src_n8n` вынесены в отдельный репозиторий:

- `~/dev/monitorsoft/voice-chat/n8n`

Текущий стек подключает образ через `stack/webrtc.drs` (`voice-chat/n8n`).

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

`~/dev/monitorsoft/voice-chat/n8n/src/settings.py` мапит runtime workflow ids (например, `echo@1.0.0`) к стабильным n8n workflow ids и webhook paths.

Формат webhook URL в этом репо:

- `<N8N_WEBHOOK_BASE_URL>/<workflowId>/webhook/<path>`

Пример:

- `http://n8n_webhook:5678/webhook/Router1o0o0o0Abc/webhook/router_1_0_0`

## Режимы запуска: Docker vs локально (IDE)

Важно: **не запускайте одновременно два экземпляра `src_n8n`** (контейнер + локальный процесс).
Иначе запросы будут “делиться” между ними (NATS queue group), и поведение будет непредсказуемым.

### Вариант (поддерживаемый): всё в Docker

- Запуск (из `~/dev/monitorsoft/voice-chat/n8n`): `docker compose -f docker/docker-compose.yml up -d --build`
- Остановка только моста: `docker compose -f docker/docker-compose.yml stop src_n8n`

Если часть сервисов вы запускаете локально (например, `src_api_gateway`), запускайте `src_n8n` в Docker с `--no-deps`,
чтобы Compose не поднял второй (docker) инстанс tools-сервиса:

- `docker compose -f docker/docker-compose.yml up -d --no-deps src_n8n`

В контейнере `src_n8n` использует:

- `N8N_WEBHOOK_BASE_URL=http://n8n_webhook:5678/webhook`
- tool proxy вызывается из n8n по `http://src_n8n:9000/tool` (адрес внутри docker-сети)

Для dry/swarm деплоя ingress для n8n настраивается в `stack/webrtc.drs`.
`src_n8n` использует внутренний URL n8n runtime в этом же стэке:
`N8N_WEBHOOK_BASE_URL=http://web-rtc-komaroff_n8n:5678/webhook`.

## Код (куда смотреть)

- NATS bridge + tool proxy: `~/dev/monitorsoft/voice-chat/n8n/src/service.py`
- Конфигурация: `~/dev/monitorsoft/voice-chat/n8n/src/settings.py`
- Контракты запросов/ответов: `~/dev/monitorsoft/voice-chat/n8n/src/contracts/*`

## Частые ошибки

### `Failed to call n8n webhook` (не подключается)

Причины:

- неверный `N8N_WEBHOOK_BASE_URL`
- `n8n_webhook` не запущен

Проверка:

- UI: `http://127.0.0.1:5679/`
- контейнеры: `docker compose -f docker/docker-compose.yml ps n8n n8n_webhook n8n_worker`

### `n8n returned 500 ... Hint: n8n must be able to reach the tool proxy URL`

Причина: workflow в n8n пытается вызвать tool proxy по URL, который не достижим из контейнера.

Решение:

- убедиться, что `src_n8n` запущен в Docker и `TOOL_PROXY_URL=http://src_n8n:9000/tool`

### `ExpressionError: Access to env vars denied` (в n8n)

Причина: в workflow используются выражения `{{$env.*}}`, но n8n запрещает доступ к env в expressions.

Решение (уже включено в compose этого репо):

- `N8N_BLOCK_ENV_ACCESS_IN_NODE=false`

Если меняли compose/окружение — проверьте env в контейнере:

- `docker compose -f docker/docker-compose.yml exec -T n8n sh -lc 'echo $N8N_BLOCK_ENV_ACCESS_IN_NODE'`

### Дубли/нестабильность при отладке

Причина: одновременно запущены два экземпляра `src_n8n` (контейнер + локальный).

Решение:

- оставить только один инстанс (не запускайте контейнер и локальный процесс одновременно)

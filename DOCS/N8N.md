# n8n (оркестрация сценариев)

## Где находится n8n-стек сейчас

Source of truth для n8n вынесен в отдельный репозиторий:

- `~/dev/monitorsoft/voice-chat/n8n`

Этот репозиторий (`webrtc-komaroff-dev`) подключает n8n-образы в `stack/webrtc.drs`:

- `voice-chat/n8n` (service `src_n8n`)
- `voice-chat/n8n-runtime` (service `n8n`)

Ingress для n8n (`/n8n`, `/n8n/webhook`, `/n8n/webhook-test`) настраивается в `stack/webrtc.drs`.
При старте сервиса `n8n` в `webrtc`-стеке автоматически выполняется
`/usr/local/bin/import-missing-workflows.sh` (импортирует только отсутствующие workflows).

## Web UI

- Локально: `http://127.0.0.1:5679/`
- Прод: `https://webrtc-komaroff.gis-master.ru/n8n/`
- При первом запуске n8n может попросить создать owner-аккаунт.

Source of truth для кода/сборки n8n остается в отдельном репозитории:

- `~/dev/monitorsoft/voice-chat/n8n`

В `voice-chat/n8n/stack/stack.drs` ingress для prod не задается.

## Демо-workflows

Стек импортирует демо-workflows из `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/*.json` и активирует их при старте:

- `router@1.0.0`
- `echo@1.0.0`
- `collect_name@1.0.0`
- `airports_and_weather@1.0.0`

Важно: `n8n_import` по умолчанию деактивирует импортированные workflows; activation jobs включают их обратно.
Если добавляете новый workflow-файл, добавьте и шаг активации в n8n-репозитории (см. `~/dev/monitorsoft/voice-chat/n8n/docker/docker-compose.yml`).

Пример end-to-end (пошагово, с payloads и указателями на код):

- `DOCS/example.md`

## Как “подтягиваются” новые сценарии при импорте только на пустой базе (Вариант A)

Вариант A означает: **источник истины — n8n UI + Postgres (volume)**. Репозиторий (`~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/*.json`) — это
**бэкап/шаблоны/начальный bootstrap**, а не “живое” хранилище.

Отсюда следует:

- Если вы **создали новый сценарий в n8n UI**, он уже “подтянулся” — потому что сохранён в базе n8n. Никакой доп. импорт при
  каждом старте не нужен.
- Если вы хотите, чтобы **новый сценарий появился на другой машине/окружении**, делайте перенос как артефакт:
  1) В n8n UI откройте workflow -> `...` -> `Download` / `Export` (экспорт JSON).
  2) Положите файл в `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/` и закоммитьте (по желанию).
  3) На целевом окружении выполните импорт в **пустую базу n8n** (или удалите старый workflow и импортируйте заново).

Практический совет для обновлений без боли:

- Версионируйте имя workflow (например, `my_scenario@1.0.0` -> `my_scenario@1.0.1`) и переключайте роутер на новую версию.
  Так вы избегаете “перезаписи” (которой в CLI импорте по сути нет) и всегда можете быстро откатиться.

## Почему workflows повторяются в списке

Причина — механизм bootstrap импорта.

В `webrtc`-стеке missing-only импорт выполняется startup-скриптом перед `n8n start`.
В `voice-chat/n8n/docker/docker-compose.yml` это реализовано отдельным сервисом `n8n_import`.
Этот CLI импорт:

- не делает “умный upsert” по имени/ID,
- может создавать новый workflow при каждом импорте,
- при этом старые workflows с тем же именем остаются в базе, поэтому в UI вы видите дубликаты.

Как с этим работать:

1) Для “чистого” состояния удалите лишние (старые) workflows через UI (меню `...` -> Delete), оставив один актуальный.
2) Если хотите, чтобы дубликаты больше не появлялись, нужно менять bootstrap стратегию (например, импортировать только
   при первом запуске/пустой базе). Это отдельная доработка.

## Что означает бейдж Published

В актуальных версиях n8n есть разделение “опубликованной” версии workflow и черновых/неопубликованных изменений.
Бейдж `Published` означает, что текущая версия workflow опубликована и именно она будет использоваться при выполнении
(в том числе в multi-process/queue режиме, где `n8n_webhook` и `n8n_worker` исполняют workflows).

## Частые ошибки

### В UI много одинаковых workflow (дубликаты)

Причина: в `~/dev/monitorsoft/voice-chat/n8n/docker/docker-compose.yml` есть bootstrap-импорт (`n8n_import`), который может добавлять workflows повторно.

Что делать сейчас (быстро):

- удалить “мертвые” workflows в UI (меню `...` -> `Delete`), оставив один актуальный

Что делать системно:

- поменять стратегию bootstrap (например, seed только на пустой базе) и перестать импортировать каждый `up`

### `Failed to call n8n webhook` / `500 Internal Server Error` при дергании webhook

Чаще всего это “внутренняя” ошибка workflow (не смог вызвать tool proxy / LLM / tools).

Что проверить:

- в контейнерах корректен `TOOL_PROXY_URL` (см. `DOCS/N8N_BRIDGE.md`)
- workflow действительно `Published` (иначе может исполняться старая/неактивная версия)

## Контракт входа/выхода workflow

Все workflows в этом репо запускаются через Webhook node (HTTP POST). Вход — JSON body:

- `{ session_id, text, edit?, runtime, trace_id, correlation_id, request_id, ts_ms }`

Последний node должен вернуть один JSON объект, совместимый с `N8nRunResponse`:

- `status`: `RUNNING|DONE|FAILED`
- `result`: string (опционально)
- `client_handler`: `{command, payload?, artifacts?}` (опционально)
- `client_events`: список `{command, payload?, artifacts?}`
- `next_runtime`: `{active_workflow_id?, pending?, context?, version}`
- `errors`: список `{code, message, details?}`

## Вызов tools из workflow

n8n напрямую с NATS не работает. Workflows вызывают tools через HTTP:

- `POST http://src_n8n:9000/tool` (адрес внутри docker-сети)

Body (ToolCallRequest):

```json
{
  "trace_id": "uuid",
  "correlation_id": "uuid",
  "request_id": "uuid",
  "session_id": "uuid",
  "ts_ms": 1730000000000,
  "tool_name": "search_airports_nearby",
  "args": { "city": "moscow", "radius_km": 250 }
}
```

Ответ — `ToolCallResponse`:

- `ok`, `data`, `artifact_key` и опционально `error`.

## Свои ноды (custom nodes) vs встроенные ноды

В этом репо нет пакета кастомных n8n-ноды.
Для сценариев рекомендуется использовать встроенные ноды:

- **Webhook**: вход в workflow (HTTP POST)
- **Function**: логика на JavaScript (без бизнес-логики в `src_agent`)
- **HTTP Request**: вызов tool proxy `src_n8n` (`{{$env.TOOL_PROXY_URL}}`)
- **IF / Merge**: ветвление и объединение

Если нужен настоящий custom node (как пакет, который ставится в n8n), это отдельная инженерная задача:
нужно разработать и поставлять node package и подключать его в контейнер n8n (volume/install).

## Создание нового сценария (workflow) максимально подробно

Ниже — рекомендуемый “копируй и адаптируй” путь.

### Шаг 0: придумайте идентификаторы

1) Runtime id (стабильный идентификатор сценария, который будет использоваться в runtime_state):

- `my_scenario@1.0.0`

2) Webhook path (стабильная строка в Webhook node):

- `my_scenario_1_0_0`

3) Стабильный n8n workflow id (поле `"id"` в JSON экспортированного workflow), например:

- `MyScenario1o0o0o0Abcd`

### Шаг 1: создайте workflow в UI n8n

1) В n8n нажмите **New Workflow**.
2) Добавьте node **Webhook**:
   - HTTP Method: `POST`
   - Path: `my_scenario_1_0_0`
   - Имя node: оставьте `Webhook` (не переименовывайте), чтобы совпадал маршрут webhook, который использует этот репо
   - Response:
     - Response Mode: `Last Node`
     - Response Data: `First Entry JSON`
3) Добавьте node **Function** с именем `Build Response` и соедините `Webhook -> Build Response`.
4) В `Build Response` соберите корректный `N8nRunResponse`. Минимальный вариант (DONE + SHOW_MESSAGE):

```js
const input = items[0].json.body || items[0].json;
return [{ json: {
  trace_id: input.trace_id,
  correlation_id: input.correlation_id || input.trace_id,
  request_id: input.request_id,
  session_id: input.session_id,
  ts_ms: Date.now(),
  status: 'DONE',
  result: '',
  client_handler: { command: 'SHOW_MESSAGE', payload: { message: 'Hello from my_scenario@1.0.0' } },
  client_events: [],
  next_runtime: {
    active_workflow_id: null,
    pending: null,
    context: input.runtime?.context || null,
    version: input.runtime?.version || 1
  },
  errors: []
}}];
```

Сохраните workflow.

### Шаг 2: экспортируйте workflow в репозиторий

В UI n8n экспортируйте workflow в JSON и положите файл:

- `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/my_scenario_1_0_0.json`

Этот репо ожидает, что workflows будут импортироваться из этой директории при старте стека.

### Шаг 3: задайте стабильный workflow id в JSON

Почему это важно:

- URL webhook, который вызывает `src_n8n`, зависит от `workflowId`.
- Для предсказуемости мы фиксируем `"id"` в JSON и используем его в `~/dev/monitorsoft/voice-chat/n8n/src/settings.py`.

Сделайте:

1) Откройте `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/my_scenario_1_0_0.json`.
2) Установите поле `"id"` в стабильное значение, например `"MyScenario1o0o0o0Abcd"`.
3) Дальше при повторных экспортах держите `"id"` таким же.

### Шаг 4: подключите workflow в `src_n8n`

Откройте `~/dev/monitorsoft/voice-chat/n8n/src/settings.py` и добавьте:

1) Константу runtime id, например:

- `WORKFLOW_MY_SCENARIO = "my_scenario@1.0.0"`

2) В `WORKFLOW_ENTITY_IDS`:

- ключ: `WORKFLOW_MY_SCENARIO`
- значение: `"MyScenario1o0o0o0Abcd"`

3) В `WORKFLOW_WEBHOOK_PATHS`:

- значение: `f"{WORKFLOW_ENTITY_IDS[WORKFLOW_MY_SCENARIO]}/webhook/my_scenario_1_0_0"`

### Шаг 5: добавьте сценарий в router allowlist

Откройте `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/router_1_0_0.json` и найдите Function node `Build LLM Request`.
В массив `allowlist_workflows` добавьте `my_scenario@1.0.0`.

Если вы используете `LLM_MODE=mock`, то для стабильного роутинга в демо-режиме добавьте эвристику в `src_llm/service.py`
(иначе LLM может никогда не выбрать ваш новый workflow).

### Шаг 6: обеспечьте активацию после импорта

`n8n_import` деактивирует workflows при импорте. Добавьте в `~/dev/monitorsoft/voice-chat/n8n/docker/docker-compose.yml` новый activation job по аналогии:

- `n8n_activate_<name>` -> `update:workflow --id=<YourStableWorkflowId> --active=true`

### Шаг 7: проверьте end-to-end

Проверьте:

- workflow возвращает валидный `N8nRunResponse` JSON
- UI отрисовывает ожидаемую команду
- `runtime_state` обновляется корректно (для сценариев с `RUNNING/pending`)

Для автоматизации добавьте тест кейс в `src_e2e/main.py`.

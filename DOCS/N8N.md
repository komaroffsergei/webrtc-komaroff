# n8n (оркестрация сценариев)

## Где находится n8n-стек сейчас

Source of truth для n8n вынесен в отдельный репозиторий:

- `~/dev/monitorsoft/voice-chat/n8n`

Этот репозиторий (`webrtc-komaroff-dev`) подключает n8n-образы в `stack/webrtc.drs`:

- `voice-chat/n8n` (service `src_n8n`)
- `voice-chat/n8n-runtime` (service `n8n`)

Ingress для n8n (`/n8n`, `/n8n/webhook`, `/n8n/webhook-test`) настраивается в `stack/webrtc.drs`.

## Web UI

- Локально: `http://127.0.0.1:5679/`
- Прод: `https://webrtc-komaroff.gis-master.ru/n8n/`
- При первом запуске n8n может попросить создать owner-аккаунт.

Source of truth для кода/сборки n8n остается в отдельном репозитории:

- `~/dev/monitorsoft/voice-chat/n8n`

В `voice-chat/n8n/stack/stack.drs` ingress для prod не задается.

## Демо-workflows

Стек синхронизирует демо-workflows из `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/*.json` при старте:

- `router@1.0.0`
- `echo@1.0.0`
- `collect_name@1.0.0`
- `airports_and_weather@1.0.0`

`n8n_import` делает канонический sync:
- импортирует эталонные JSON с фиксированными `id/path`,
- деактивирует конфликтующие workflows с тем же webhook path и другим `id`,
- публикует и активирует канонические workflows.

Если добавляете новый workflow-файл, добавьте его в `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/`
и синк применит его автоматически.

Пример end-to-end (пошагово, с payloads и указателями на код):

- `DOCS/example.md`

## Как теперь подтягиваются сценарии

Источник истины для системных сценариев — JSON-файлы в
`~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/`.

При старте стека `n8n_import` приводит БД к каноническому состоянию:
- системные workflows синхронизируются из JSON,
- конфликтные дубли по webhook path деактивируются,
- канонические workflows публикуются и активируются.

Если вы меняете сценарий в UI и хотите сохранить его как эталон, экспортируйте JSON обратно в этот каталог.

## Почему workflows могут повторяться в списке

При ручном импорте через UI/CLI можно создать дубли.
Автосинк `n8n_import` деактивирует конфликты по webhook path, но старые дубли могут оставаться в списке как `Inactive`.

Рекомендация: периодически удалять такие дубли через UI (`... -> Delete`), оставляя канонические workflows.

## Что означает бейдж Published

В актуальных версиях n8n есть разделение “опубликованной” версии workflow и черновых/неопубликованных изменений.
Бейдж `Published` означает, что текущая версия workflow опубликована и именно она будет использоваться при выполнении
(в том числе в multi-process/queue режиме, где `n8n_webhook` и `n8n_worker` исполняют workflows).

## Частые ошибки

### В UI много одинаковых workflow (дубликаты)

Причина: обычно ручной импорт через UI/CLI или старые данные в БД.

Что делать сейчас (быстро):

- удалить “мертвые” workflows в UI (меню `...` -> `Delete`), оставив канонические.

Что делать системно:

- использовать канонический `n8n_import` при каждом старте (он деактивирует конфликты по webhook path и активирует эталонные workflows).

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

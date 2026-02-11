# Пример (end-to-end): "Найди ближайший аэропорт"

Этот документ объясняет, как сейчас работает запрос "найди ближайший аэропорт" в текущей архитектуре (n8n orchestration + NATS),
где используется LLM, какие subjects/контракты участвуют, и как это воспроизвести локально.

## 0) Предпосылки

### 0.1 Роли сервисов (кто за что отвечает)

- `src_front` (локально): UI. Отправляет текст в `src_core`, подписывается на `nats.events.<user_id>`.
- `src_core` (локально): HTTP ingress для UI. Принимает `/core/message`, делает NATS req-reply в `src_agent`.
- `src_agent` (локально): тонкий раннер. Достаёт runtime из Postgres, вызывает `src_n8n` по NATS, публикует UI-команды/события.
- `src_n8n` (Docker): мост NATS <-> n8n + tool proxy HTTP endpoint для workflows.
- `n8n` (Docker): хранит и исполняет workflows (router + сценарии).
- `src_llm` (Docker): LLM gateway, NATS req-reply `nats.llm.<user_id>` (в dev обычно `LLM_MODE=mock`).
- `src_postgres` (Docker): хранит runtime_state (agent) и n8n schema `n8n` (n8n).
- `nats` (Docker): транспорт межсервисного обмена.
- `src_api_gateway` (локально): демо-tools по NATS (`nats.tools.*`) + HTTP mock API для `init_map` в `src_core`.

### 0.2 Subjects (канонические)

Смотрите `src_shared/contracts/subjects.py`.

- `nats.agent.<user_id>`: `src_core` -> `src_agent` (req-reply)
- `nats.events.<user_id>`: `src_agent` -> `src_front` (pub-sub)
- `nats.n8n.run`: `src_agent` -> `src_n8n` (req-reply)
- `nats.llm.<user_id>`: `src_n8n` -> `src_llm` (req-reply) (через tool proxy)
- `nats.tools.<name>`: `src_n8n` -> tool сервисы, в демо это `src_api_gateway` (req-reply)

### 0.3 Контракты сообщений (Pydantic)

- Вход в агент: `AgentInboundRequest` / `AgentInboundResponse` (`src_shared/contracts/agent.py`)
- Запуск workflow: `N8nRunRequest` / `N8nRunResponse` (`src_shared/contracts/n8n.py`)
- Вызов tool/LLM из n8n: `ToolCallRequest` / `ToolCallResponse` (`src_shared/contracts/tools.py`)
- Вызов LLM: `LlmRequest` / `LlmResponse` (`src_shared/contracts/llm.py`)

Во всех envelope-пейлоадах есть: `trace_id`, `correlation_id`, `request_id`, `session_id`, `ts_ms`.

## 1) Как запустить окружение (гибрид: часть локально, n8n-часть в Docker)

### 1.1 Docker (n8n + мост + LLM + infra)

Важно: если `src_api_gateway` у вас локально, запускайте `src_n8n` в Docker с `--no-deps`, иначе Compose поднимет
ещё и docker-версию `src_api_gateway`, и tool-вызовы будут "делиться" между инстансами (NATS queue group).

Команды по одному сервису (из корня репо):

```bash
docker compose -f docker/docker-compose.yml up -d nats
docker compose -f docker/docker-compose.yml up -d src_postgres
docker compose -f docker/docker-compose.yml up -d redis
docker compose -f docker/docker-compose.yml up -d src_llm

# n8n: при старте выполнит bootstrap импорт workflows (n8n_import) и activation jobs (n8n_activate_*)
docker compose -f docker/docker-compose.yml up -d n8n
docker compose -f docker/docker-compose.yml up -d n8n_webhook
docker compose -f docker/docker-compose.yml up -d n8n_worker

# запускаем мост без deps, чтобы не стартовать docker tools (src_api_gateway)
docker compose -f docker/docker-compose.yml up -d --no-deps src_n8n
```

Проверки:

- n8n UI: `http://127.0.0.1:5679/`
- NATS TCP: `nats://127.0.0.1:4222`
- `src_n8n` tool proxy в docker-сети: `http://src_n8n:9000/tool` (используется workflows)

### 1.2 Локально (UI + core + agent + tools)

Минимальные env:

- `USER_ID=user123` (должен совпадать с UI/subjects)
- `NATS_URL=nats://127.0.0.1:4222`
- `DATABASE_URL=postgresql://mcp:mcp_pass@127.0.0.1:5432/mcp`

Старт:

```bash
# tools + mock API для init_map (src_core ожидает API_URL; по умолчанию 8101)
API_PORT=8101 python src_api_gateway/main.py

python -m src_agent.main
python -m src_core.main

cd src_front
npm install
npm run dev
```

## 2) Пример запроса (UI): "найди ближайший аэропорт"

### 2.1 Вариант 1: в одном сообщении есть город и радиус

Пример текста:

> "Покажи аэропорты в Москве в радиусе 250 км"

Ожидаемое поведение:

- router выберет `airports_and_weather@1.0.0`
- сценарий вызовет 2 tools параллельно:
  - `search_airports_nearby(city='Москва', radius_km=250)`
  - `get_weather(city='Москва')`
- UI получит `SHOW_AIRPORTS` с данными `airports[]` и `weather{...}`

### 2.2 Вариант 2: радиус не указан (user-in-the-loop)

Пример текста:

> "Покажи аэропорты в Москве"

Ожидаемое поведение:

1) первый ответ: `status=RUNNING` + `ASK_USER_INPUT` ("Укажите радиус в км.")
2) второе сообщение пользователя (например `250`) продолжит тот же workflow и вернёт `DONE` + `SHOW_AIRPORTS`

## 3) Пошаговый трейс: что происходит под капотом

### 3.1 UI -> src_core (HTTP)

UI отправляет HTTP:

- `POST /core/message` (см. `src_core/main.py`)
- body: `{ "text": "...", "session_id": "...?" }`

Код отправки в агент через NATS: `src_core/handlers/handle_transcription.py`.

### 3.2 src_core -> src_agent (NATS req-reply)

`src_core` делает `nc.request()` в subject:

- `nats.agent.<user_id>`

Payload соответствует `AgentInboundRequest` (`src_shared/contracts/agent.py`).

### 3.3 src_agent: runtime + вызов n8n через мост

`src_agent` (`src_agent/agent.py` + `src_agent/service.py`) делает:

1) ensure `sessions` row (даже если `session_id` пришёл извне)
2) load `runtime_state` из Postgres
3) NATS req-reply в `nats.n8n.run` (`N8nRunRequest`)
4) сохраняет `next_runtime` в Postgres (optimistic lock по `version`)
5) публикует UI-команды в `nats.events.<user_id>`

### 3.4 src_agent -> src_n8n (NATS req-reply)

Subject:

- `nats.n8n.run`

Payload: `N8nRunRequest` (`src_shared/contracts/n8n.py`).

### 3.5 src_n8n -> n8n (HTTP webhook)

`src_n8n` (`src_n8n/service.py` + `src_n8n/settings.py`) выбирает webhook path:

- если `runtime.active_workflow_id` задан, продолжает его
- иначе вызывает `router@1.0.0`

HTTP вызывается в `n8n_webhook` по `N8N_WEBHOOK_BASE_URL=http://n8n_webhook:5678/webhook`.

### 3.6 router workflow: где используется LLM и зачем

Файл: `docker/n8n/workflows/router_1_0_0.json`.

Роль LLM в router:

- единственная задача: выбрать `workflow_id` из allowlist на основе `text` и `runtime.context`
- никакой логики сценариев в `src_agent` нет

Как router вызывает LLM:

1) `Build LLM Request` собирает `ToolCallRequest`:
   - `tool_name="llm.routing_decision"`
   - `args.input={ text, context_tail, allowlist_workflows }`
2) `Call LLM` делает HTTP `POST http://src_n8n:9000/tool`
3) `src_n8n` распознаёт `tool_name` с префиксом `llm.` и делает NATS request в `nats.llm.<user_id>`
4) `src_llm` возвращает `LlmResponse` c `data={workflow_id, reason, confidence}` (см. `src_shared/contracts/llm.py`)
5) router валидирует, что `workflow_id` входит в allowlist, и вызывает выбранный сценарий

Где именно находится LLM роутинг:

- mock-логика роутинга (dev): `src_llm/service.py` (mode `routing_decision`)
- схема ответа: `RoutingDecisionData` (`src_shared/contracts/llm.py`)

### 3.7 airports_and_weather workflow: инструменты и user-in-the-loop

Файл: `docker/n8n/workflows/airports_and_weather_1_0_0.json`.

Ключевые узлы:

- `Extract Params` (JS): грубо вытаскивает `city` и `radius_km` из текста/`runtime.pending` (без LLM)
- `Ask City` / `Ask Radius`: если поля отсутствуют, возвращает `RUNNING` + `ASK_USER_INPUT` и заполняет `next_runtime.pending`
- `Call Airports Tool` и `Call Weather Tool`:
  - оба делают `POST http://src_n8n:9000/tool`
  - `tool_name`: `search_airports_nearby` и `get_weather`
  - выполняются параллельно (ветвление в n8n графе)
- `Build Response`: формирует `N8nRunResponse` (`DONE` + `SHOW_AIRPORTS`)

### 3.8 tool proxy: n8n -> src_n8n -> NATS tools

Tool proxy endpoint:

- HTTP: `POST http://src_n8n:9000/tool` (см. `src_n8n/service.py`)

Контракт запроса/ответа:

- `ToolCallRequest` / `ToolCallResponse` (`src_shared/contracts/tools.py`)

Дальше `src_n8n` делает NATS request:

- tools: `nats.tools.<tool_name>`
- llm: `nats.llm.<user_id>` (когда `tool_name` начинается с `llm.`)

### 3.9 Ответ назад в UI

1) n8n возвращает `N8nRunResponse` в `src_n8n`
2) `src_n8n` возвращает его в `src_agent` по `nats.n8n.run`
3) `src_agent`:
   - сохраняет `next_runtime` в Postgres
   - публикует команды в `nats.events.<user_id>` (см. `_publish_ui_events` в `src_agent/service.py`)
4) UI получает команды из NATS WS и рисует результат

## 4) Примеры пейлоадов (сокращённые)

### 4.1 ToolCallRequest для LLM (router -> tool proxy)

```json
{
  "trace_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "correlation_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "request_id": "f3b1a0b7-1b2c-4d5e-8f9a-001122334455",
  "session_id": "d2c1b0a9-8899-4a3b-8c7d-6e5f4a3b2c1d",
  "ts_ms": 1760000000000,
  "tool_name": "llm.routing_decision",
  "args": {
    "input": {
      "text": "Покажи аэропорты в Москве в радиусе 250 км",
      "context_tail": {},
      "allowlist_workflows": ["echo@1.0.0", "collect_name@1.0.0", "airports_and_weather@1.0.0"]
    },
    "constraints": { "temperature": 0.0 }
  }
}
```

### 4.2 LlmResponse (src_llm -> src_n8n)

```json
{
  "trace_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "correlation_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "request_id": "f3b1a0b7-1b2c-4d5e-8f9a-001122334455",
  "session_id": "d2c1b0a9-8899-4a3b-8c7d-6e5f4a3b2c1d",
  "ts_ms": 1760000000000,
  "ok": true,
  "data": { "workflow_id": "airports_and_weather@1.0.0", "reason": "Airport/weather keywords detected.", "confidence": 0.9 },
  "error": null
}
```

### 4.3 ToolCallRequest для tools (scenario -> tool proxy)

```json
{
  "trace_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "correlation_id": "6d5d9c2c-1f5b-4c3a-9f2b-1b2c3d4e5f60",
  "request_id": "f3b1a0b7-1b2c-4d5e-8f9a-001122334455",
  "session_id": "d2c1b0a9-8899-4a3b-8c7d-6e5f4a3b2c1d",
  "ts_ms": 1760000000000,
  "tool_name": "search_airports_nearby",
  "args": { "city": "Москва", "radius_km": 250 }
}
```

## 5) Где смотреть код (короткий список)

- router workflow + LLM tool call: `docker/n8n/workflows/router_1_0_0.json`
- airports сценарий + tools: `docker/n8n/workflows/airports_and_weather_1_0_0.json`
- tool proxy + NATS bridge: `src_n8n/service.py`
- LLM gateway: `src_llm/service.py`
- tools (NATS): `src_api_gateway/main.py`
- agent runner: `src_agent/agent.py` и публикация UI events: `src_agent/service.py`
- core ingress: `src_core/main.py` и `src_core/handlers/handle_transcription.py`


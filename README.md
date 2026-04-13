# webrtc-komaroff

Локальный стек WebRTC + NATS + workflow runtime.

## Сервисы

- `src_front` — веб UI.
- `src_core` — обработка сессии/голоса и работа с фронтом.
- `src_agent` — оркестратор пользовательского шага, хранит runtime в Postgres.
- `src_langgraph` — runtime сценариев на LangGraph.
- `src_langgraph_rb` — Ruby workflow runtime for migrated сценариев (`free_speech`, `where_my_flight`, `find_nearest_airport`) plus DSL/catalog.
- `src_langgraph_rb_node` — Ruby workflow runtime на `AsyncGraph` с native graph authoring и direct-start сценариев.
- `src_llm` — gateway к модели (Ollama/remote).
- `src_api_gateway` — tools (`nats.tools.*`) для сценариев.
- `src_postgres` — БД runtime.
- `nats` — шина сообщений.

Каноническая карта сервисов, проектов, протоколов, subject-ов, payload-ов и внешнего `rag-stack`: [`DOCS/ARCHITECTURE.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/ARCHITECTURE.md)

## NATS subjects

Краткая сводка:

- `nats.agent.<user_id>` — вход в `src_agent`.
- `nats.events.<user_id>` — события в UI.
- `nats.workflow.run.python` — запрос на выполнение Python runtime.
- `nats.workflow.health.python` — health Python runtime.
- `nats.workflow.run.ruby` — запрос на выполнение Ruby runtime.
- `nats.workflow.health.ruby` — health Ruby runtime.
- `nats.workflow.run.ruby.node` — запрос на выполнение AsyncGraph Ruby runtime.
- `nats.workflow.health.ruby.node` — health AsyncGraph Ruby runtime.
- `nats.llm.<user_id>` — вызовы LLM.
- `nats.tools.<tool_name>` — вызовы инструментов.

Полный registry, включая live/file ASR и `rag-stack` bridge subjects, см. в [`DOCS/ARCHITECTURE.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/ARCHITECTURE.md) и [`DOCS/NATS.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/NATS.md).

## Быстрый запуск (Docker)

```bash
cd docker
docker compose down --remove-orphans
docker compose up -d --build
```

Локальный Docker по умолчанию использует Ruby runtime. Переключатель собран в одном месте: [docker/.env](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/docker/.env).
В нем должны совпадать `COMPOSE_PROFILES` и workflow subject'ы:

```bash
COMPOSE_PROFILES=langgraph_rb
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.ruby
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.ruby
```

Для Python runtime:

```bash
COMPOSE_PROFILES=langgraph
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.python
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.python
```

Для `src_langgraph_rb_node`:

```bash
COMPOSE_PROFILES=langgraph_rb_node
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.ruby.node
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.ruby.node
```

После смены runtime делай только clean-start:

```bash
cd docker
docker compose down --remove-orphans
docker compose up -d --build
```

`src_agent` использует только настроенные `NATS_WORKFLOW_*_SUBJECT`; скрытого fallback между Ruby и Python runtime больше нет.
То же правило действует и для `src_langgraph_rb_node`: переключение делается только subject-ом.

Если Docker отвечает `failed to set up container networking ... network ... not found`, это stale state у старого контейнера после пересоздания сети. Нужен `docker compose down --remove-orphans`; если контейнер остался, удали его через `docker rm -f <container>`, потом снова `docker compose up -d --build`.

Для Docker-сервисов используется `NATS_URL_INTERNAL` (по умолчанию `nats://nats:4222`).
Если в `docker/.env` у вас задан `NATS_URL=nats://localhost:4222` для запуска с хоста, это больше не ломает межконтейнерное подключение.

Для NATS2Ollama endpoint без auth:
```bash
cd docker
export OLLAMA_URL=https://nats2ollama.gis-master.ru
docker compose up -d --build
```
Важно: base URL не должен содержать `/api/chat`, иначе `src_llm` получит `405 Method Not Allowed`.

Открыть:
- UI: `http://127.0.0.1:8080/`
- Core: `http://127.0.0.1:8000/core`
- API Gateway: `http://127.0.0.1:8101/api`
- NATS WS: `ws://127.0.0.1:9222`

В deploy stack сейчас есть два file-маршрута:

- `/whisper` для plain transcription без diarization
- `/whisper-diarize` для combined flow: plain text + speaker separation

Оба маршрута публикуют NATS file-job, worker нормализует audio в `mono 16k`, режет его на чанки и отправляет transcription в `linto_stt_whisper_http`. Только `/whisper-diarize` дополнительно ждёт `pyannote_diarization` и показывает speaker progress/result через отдельные diarization subjects.

Режимы ASR в этом стэке сейчас такие:
- live voice: `WebRTC -> src_core -> inference.whisper.stream.* -> stt_whisper_to_nats -> LinTO HTTP -> inference.whisper.text.* -> src_core`
- `/whisper` file mode: `Browser -> HTTP upload + direct NATS WS -> inference.whisper.file.* -> file worker -> sequential chunked LinTO HTTP`
- `/whisper-diarize` combined file mode: `Browser -> HTTP upload + direct NATS WS -> inference.whisper.file.* + inference.whisper.file.diar_text.* -> file worker -> LinTO HTTP + pyannote diarization`

Подробная архитектура, схемы сервисов, протоколы, payload-ы и внешние интеграции: [`DOCS/ARCHITECTURE.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/DOCS/ARCHITECTURE.md)
Ruby runtime code map: [`src_langgraph_rb/CODEMAP.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/CODEMAP.md)
AsyncGraph runtime docs: [`src_langgraph_rb_node/README.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb_node/README.md), [`src_langgraph_rb_node/CODEMAP.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb_node/CODEMAP.md)

## Docker + отладка (PyCharm Remote Debug)

`debugpy` включается только через override-файл, обычный запуск без отладки не меняется.

```bash
cd docker
cp .env.debug.example .env.debug
# обязательно: абсолютный путь к корню репозитория на хосте
# пример:
# PYCHARM_PROJECT_ROOT=/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff
export COMPOSE_PROFILES=langgraph
export NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.python
export NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.python
docker compose --env-file .env --env-file .env.debug \
  -f docker-compose.yml -f docker-compose.debug.yml \
  up -d --build
```

Важно: не запускай debug-стек без `-d` на длительную сессию. В attached-режиме (`up` без `-d`) закрытие/прерывание этой команды останавливает контейнеры, и все PyCharm attach-сессии сразу рвутся.

Порты отладки:
- `src_core`: `127.0.0.1:5671`
- `src_agent`: `127.0.0.1:5672`
- `src_api_gateway`: `127.0.0.1:5673`
- `src_langgraph`: `127.0.0.1:5674`
- `src_llm`: `127.0.0.1:5675`
- эти порты должны быть свободны на хосте для `Python Remote Debug` в PyCharm (docker их не публикует).

Если нужен стоп на старте до подключения IDE, выстави в `docker/.env.debug`:
- `DEBUGPY_WAIT_FOR_CLIENT=1`
- при этом сервисы не начнут слушать HTTP/NATS до attach, и до подключения дебаггера `src_front` может отвечать `502` на `/core/*` — это ожидаемо.
- при `DEBUGPY_WAIT_FOR_CLIENT=0` сервисы стартуют сразу, а attach произойдёт в фоне, когда запустишь `Attach ...` конфиг в PyCharm.
- `PYCHARM_REDIRECT_OUTPUT=0` рекомендуется для стабильного переподключения (логи смотри через `docker compose logs`).
- `PYCHARM_PATCH_MULTIPROCESSING=0` рекомендуется оставить по умолчанию (стабильнее attach). Включай `1` только если нужно дебажить дочерние `multiprocessing` процессы.

В проект уже добавлены shared PyCharm run-конфиги (`.run/Attach_*.run.xml`) для `Attach` к каждому сервису.
В них уже включен параллельный запуск (`singleton=false`), поэтому можно одновременно подключаться к нескольким сервисам.

## Локальный запуск Python-сервисов

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_core/requirements.txt \
  -r src_agent/requirements.txt \
  -r src_llm/requirements.txt \
  -r src_langgraph/requirements.txt \
  -r src_api_gateway/requirements.txt
```

Сначала подними инфраструктуру:

```bash
cd docker
docker compose up -d nats src_postgres
```

Потом в отдельных терминалах:

```bash
python src_api_gateway/main.py
python -m src_llm.main
python -m src_langgraph.main
python -m src_agent.main
python -m src_core.main
```

UI:

```bash
cd src_front
npm install
npm run dev
```

## Контракты сообщений

Модели в `src_shared/contracts`:
- `AgentInboundRequest` / `AgentInboundResponse`
- `WorkflowRunRequest` / `WorkflowRunResponse`
- `ToolCallRequest` / `ToolCallResponse`
- `LlmRequest` / `LlmResponse`

Во всех envelope полях используются:
- `trace_id` — трассировка по всей цепочке вызовов.
- `correlation_id` — связывание связанных операций/веток.
- `request_id` — идемпотентность конкретного запроса.
- `session_id` — состояние диалога пользователя.
- `ts_ms` — время события.

## Документация

- `DOCS/ARCHITECTURE.md`
- `DOCS/START_HERE.md`
- `DOCS/QUICKSTART.md`
- `DOCS/AGENT.md`
- `DOCS/LLM.md`
- `DOCS/LANGGRAPH.md`
- `DOCS/API_GATEWAY.md`
- `DOCS/NATS.md`
- `DOCS/POSTGRES.md`
- `src_langgraph/README.md`
- `src_langgraph_rb/README.md`
- `src_langgraph_rb/CODEMAP.md`
- `src_langgraph_rb_node/README.md`
- `src_langgraph_rb_node/CODEMAP.md`

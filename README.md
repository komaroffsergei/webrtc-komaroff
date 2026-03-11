# webrtc-komaroff

Локальный стек WebRTC + NATS + LangGraph runtime.

## Сервисы

- `src_front` — веб UI.
- `src_core` — обработка сессии/голоса и работа с фронтом.
- `src_agent` — оркестратор пользовательского шага, хранит runtime в Postgres.
- `src_langgraph` — runtime сценариев на LangGraph.
- `src_llm` — gateway к модели (Ollama/remote).
- `src_api_gateway` — tools (`nats.tools.*`) для сценариев.
- `src_postgres` — БД runtime.
- `nats` — шина сообщений.

## NATS subjects

- `nats.agent.<user_id>` — вход в `src_agent`.
- `nats.events.<user_id>` — события в UI.
- `nats.workflow.run` — запрос на выполнение сценария.
- `nats.workflow.health` — health runtime.
- `nats.llm.<user_id>` — вызовы LLM.
- `nats.tools.<tool_name>` — вызовы инструментов.

## Быстрый запуск (Docker)

```bash
cd docker
docker compose --profile langgraph up -d --build
```

Для Docker-сервисов используется `NATS_URL_INTERNAL` (по умолчанию `nats://nats:4222`).
Если в `docker/.env` у вас задан `NATS_URL=nats://localhost:4222` для запуска с хоста, это больше не ломает межконтейнерное подключение.

Для NATS2Ollama endpoint без auth:
```bash
cd docker
export OLLAMA_URL=https://nats2ollama.gis-master.ru
docker compose --profile langgraph up -d --build
```
Важно: base URL не должен содержать `/api/chat`, иначе `src_llm` получит `405 Method Not Allowed`.

Открыть:
- UI: `http://127.0.0.1:8080/`
- Core: `http://127.0.0.1:8000/core`
- API Gateway: `http://127.0.0.1:8101/api`
- NATS WS: `ws://127.0.0.1:9222`

В stack-конфиге `webrtc.drs` маршрут `/whisper` включает server-side file transcription mode для `wav/mp3/m4a/mp4`. Он загружает исходный файл в gateway, создаёт NATS file-job, worker вырезает audio-only поток, нормализует его в `mono 16k`, режет на чанки и отправляет их параллельно в file-only LinTO HTTP backend-ы, а браузер получает progress/result напрямую из NATS WS по session-scoped file subjects, не меняя live voice pipeline `inference.whisper.*`.

Режимы ASR в этом стэке сейчас такие:
- live voice: `WebRTC -> NATS -> stt_whisper_to_nats -> LinTO websocket -> NATS`
- `/whisper` file mode: `Browser -> HTTP upload + direct NATS WS -> gateway -> NATS file job -> parallel chunked LinTO HTTP -> strict-prefix merge`
- `/whisper` stream debug: `Browser -> WebUI websocket -> NATS -> LinTO websocket`

Подробная схема всех режимов: [`ASR_BRIDGE_FLOW.md`](/home/komaroff/dev/monitorsoft/voice-chat/ASR_BRIDGE_FLOW.md)

## Docker + отладка (PyCharm Remote Debug)

`debugpy` включается только через override-файл, обычный запуск без отладки не меняется.

```bash
cd docker
cp .env.debug.example .env.debug
# обязательно: абсолютный путь к корню репозитория на хосте
# пример:
# PYCHARM_PROJECT_ROOT=/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff
docker compose --env-file .env --env-file .env.debug \
  -f docker-compose.yml -f docker-compose.debug.yml \
  --profile langgraph up -d --build
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

- `DOCS/START_HERE.md`
- `DOCS/QUICKSTART.md`
- `DOCS/AGENT.md`
- `DOCS/LLM.md`
- `DOCS/LANGGRAPH.md`
- `DOCS/API_GATEWAY.md`
- `DOCS/NATS.md`
- `DOCS/POSTGRES.md`
- `DOCS/E2E.md`
- `src_langgraph/README.md`

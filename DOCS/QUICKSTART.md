# QUICKSTART

## Docker (рекомендуется)

```bash
cd docker
docker compose --profile langgraph up -d --build
```

Проверка:
- Front: `http://127.0.0.1:8080/`
- Core: `http://127.0.0.1:8000/core`
- API: `http://127.0.0.1:8101/api`
- NATS WS: `ws://127.0.0.1:9222`

Для deploy-стека `webrtc.drs` маршрут `/whisper` теперь включает отдельный WebUI file-mode:
- принимает `wav`, `mp3`, `m4a`, `mp4`
- создаёт async file-job через NATS, режет long-file audio на backend-чанки и отдаёт прогресс плюс финальный plain text
- не меняет live voice ASR path `inference.whisper.*`

Текущие режимы ASR:
- live voice: `WebRTC -> NATS -> stt_whisper_to_nats(Phraser) -> LinTO HTTP`
- `/whisper` file mode: `Browser -> bridge upload -> NATS file job -> chunked LinTO HTTP`

Подробная архитектура, схемы сервисов, payload-ы и code map: [`ASR_BRIDGE_FLOW.md`](/home/komaroff/dev/monitorsoft/voice-chat/ASR_BRIDGE_FLOW.md)

NATS2Ollama endpoint (без auth):
```bash
cd docker
export OLLAMA_URL=https://nats2ollama.gis-master.ru
docker compose --profile langgraph up -d --build
```
Важно: указывай базовый URL без `/api/chat`.

## Docker + debug (PyCharm)

1. Подготовить debug-env:

```bash
cd docker
cp .env.debug.example .env.debug
# обязательно задай абсолютный путь к корню репозитория:
# PYCHARM_PROJECT_ROOT=/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff
```

2. Запустить stack в debug-режиме:

```bash
docker compose --env-file .env --env-file .env.debug \
  -f docker-compose.yml -f docker-compose.debug.yml \
  --profile langgraph up -d --build
```

Важно: для долгой debug-сессии используй именно `-d`. Если запускать `up` без `-d`, завершение/прерывание этой команды останавливает контейнеры и все attach-сессии в PyCharm.

3. Debug-порты сервисов:
- `src_core`: `5671`
- `src_agent`: `5672`
- `src_api_gateway`: `5673`
- `src_langgraph`: `5674`
- `src_llm`: `5675`
- Эти порты должны быть свободны на хосте (их слушает PyCharm `Python Remote Debug`).

4. PyCharm attach:
- Конфигурация: `Python Remote Debug` (по одному на сервис/порт).
- Host: `127.0.0.1`.
- Port: из списка выше.
- Готовые shared-конфиги уже лежат в `.run/Attach_*.run.xml`.
- Для одновременной отладки нескольких сервисов запускай несколько `Attach ...` конфигов параллельно (в shared-конфигах это уже разрешено).
- Path mappings:
  - `src_core` -> `/app/src_core`
  - `src_agent` -> `/app/src_agent`
  - `src_api_gateway` -> `/app`
  - `src_langgraph` -> `/app/src_langgraph`
  - `src_llm` -> `/app/src_llm`
  - `src_shared` -> `/app/src_shared`

5. Если нужен стоп на старте до attach, поставь `DEBUGPY_WAIT_FOR_CLIENT=1` в `docker/.env.debug`.
   До attach сервисы не поднимают свои порты, поэтому `502` на `/core/*` в этот момент — ожидаемое поведение.
   При `DEBUGPY_WAIT_FOR_CLIENT=0` сервисы стартуют сразу, а attach можно включить позже (подключение в фоне).
   Для стабильного переподключения оставь `PYCHARM_REDIRECT_OUTPUT=0` (логи смотри через `docker compose logs`).
   Для стабильного attach оставь `PYCHARM_PATCH_MULTIPROCESSING=0` (по умолчанию). Значение `1` включай только если нужен дебаг дочерних `multiprocessing` процессов.

## Локально через IDE (гибрид)

1. Поднять инфраструктуру:

```bash
cd docker
docker compose up -d nats src_postgres
```

2. Установить зависимости:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_agent/requirements.txt \
  -r src_langgraph/requirements.txt \
  -r src_llm/requirements.txt \
  -r src_api_gateway/requirements.txt \
  -r src_core/requirements.txt
```

3. Запустить сервисы:

```bash
python src_api_gateway/main.py
python -m src_llm.main
python -m src_langgraph.main
python -m src_agent.main
python -m src_core.main
```

4. Для UI:

```bash
cd src_front
npm install
npm run dev
```

## Smoke-фразы

1. `где мой рейс`
2. `SU123`
3. `найди аэропорт`
4. `как дела`

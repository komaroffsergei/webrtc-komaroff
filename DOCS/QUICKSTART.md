# Быстрый старт (локальная разработка)

Этот документ отвечает на вопросы "как быстро поднять стек" и "как запускать два репозитория без override/cat/env-хака".

## 0) Ключевые порты (хост-машина)

- NATS TCP: `nats://127.0.0.1:14222`
- NATS WebSocket: `ws://127.0.0.1:9222`
- Postgres: `127.0.0.1:5432` (db `mcp`, user `mcp`, pass `mcp_pass`)
- Front: `http://127.0.0.1:8080/`
- n8n UI: `http://127.0.0.1:5679/`

Важно: n8n-стек и bridge вынесены в отдельный репозиторий `~/dev/monitorsoft/voice-chat/n8n`.
В этом репо (`webrtc-komaroff-dev`) n8n bridge подключается как образ в `stack/webrtc.drs`.

## 1) Рекомендуемый запуск в 2 терминала (Docker + Docker)

Порядок: сначала поднимите `webrtc-komaroff-dev` (он дает NATS/Postgres), потом `voice-chat/n8n`.

### Терминал 1 (в `~/dev/monitorsoft/webrtc-komaroff-dev`)

```bash
docker compose -f docker/docker-compose.yml down -v --remove-orphans
docker compose -f docker/docker-compose.yml up -d --build
```

### Терминал 2 (в `~/dev/monitorsoft/voice-chat/n8n`)

```bash
docker compose -f docker/docker-compose.yml down -v --remove-orphans
docker compose -f docker/docker-compose.yml up -d --build
```

Проверка:

- `http://127.0.0.1:8080/` (front)
- `http://127.0.0.1:5679/` (n8n UI)
- `docker compose -f docker/docker-compose.yml ps` в каждой директории

В этом режиме ничего менять не нужно:

- `REGISTRY_HOST` / `CI_COMMIT_BRANCH` уже имеют defaults в compose.
- `voice-chat/n8n` по умолчанию подключается к `host.docker.internal:14222/5432`.
- `webrtc` теперь публикует `4222` и `5432` на хост, чтобы второй проект подключался без override.

## 2) Локальный n8n внутри webrtc (legacy-режим)

Если нужен старый режим (runtime n8n внутри этого репо), он теперь вынесен в профиль `local-n8n`:

```bash
docker compose -f docker/docker-compose.yml --profile local-n8n up -d --build
```

По умолчанию (`up` без профиля) локальные `src_n8n/n8n/n8n_webhook/n8n_worker` в этом репо не стартуют.

## 3) Вариант IDE: часть сервисов запускать локально

### 3.1 Поднять инфраструктуру

```bash
docker compose -f docker/docker-compose.yml up -d nats src_postgres
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml up -d --build
```

Если вам нужны демо-tools:

```bash
docker compose -f docker/docker-compose.yml up -d src_api_gateway
```

### 3.2 Локальный Python env

Из корня репо:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_agent/requirements.txt -r src_llm/requirements.txt -r src_api_gateway/requirements.txt
```

### 3.3 Какие env выставить

Минимальный набор для запуска локально (в шелле или в `.env` файлов сервиса):

- `NATS_URL=nats://127.0.0.1:14222`
- `DATABASE_URL=postgresql://mcp:mcp_pass@127.0.0.1:5432/mcp`
- `USER_ID=user123` (должен совпадать с UI/stack)

### 3.4 Как запускать сервисы напрямую

```bash
python src_api_gateway/main.py
python -m src_llm.main
python -m src_agent.main
```

Если используете UI (`src_front`), обычно также нужен `src_core` в Docker или локально (см. `DOCS/CORE.md`).

## 4) Когда нужно перезапускать контейнеры

- Поменяли `N8N_BLOCK_ENV_ACCESS_IN_NODE` -> пересоздавайте `n8n`, `n8n_webhook`, `n8n_worker`.
- Поменяли `N8N_WEBHOOK_BASE_URL` в `src_n8n` (локальный режим) -> перезапустите `src_n8n`.
- Поменяли `NATS_URL`/`DATABASE_URL` -> перезапустите соответствующий сервис.

## 5) Импорт/обновление workflows

Workflows лежат в `~/dev/monitorsoft/voice-chat/n8n/docker/n8n/workflows/*.json`.

Импорт:

```bash
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml run --rm n8n_import
```

Важно: CLI импорт деактивирует workflows. Чтобы включить обратно, запустите activation jobs:

```bash
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_router
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_echo
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_collect_name
cd ~/dev/monitorsoft/voice-chat/n8n && docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_airports_weather
```

## 6) Быстрый smoke / E2E

Dockerized E2E runner:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

## 7) Пример end-to-end (как устроено под капотом)

Подробный разбор сценария "найди ближайший аэропорт" (LLM routing + tools + user-in-the-loop):

- `DOCS/example.md`

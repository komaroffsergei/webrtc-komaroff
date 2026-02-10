# Быстрый старт (локальная разработка)

Этот документ отвечает на вопросы "как быстро поднять стек" и "что менять в env при локальном запуске".

Важно: не запускайте одновременно два экземпляра одного сервиса (контейнер + процесс из IDE), иначе NATS сообщения
будут "делиться" между ними и поведение станет нестабильным.

## 0) Ключевые порты (хост-машина)

- NATS TCP: `nats://127.0.0.1:4222`
- NATS WebSocket: `ws://127.0.0.1:9222`
- Postgres: `127.0.0.1:5432` (db `mcp`, user `mcp`, pass `mcp_pass`)
- Front: `http://127.0.0.1:8080/`
- n8n UI: `http://127.0.0.1:5679/`

## 1) Вариант A (рекомендуемый): все сервисы в Docker

```bash
docker compose -f docker/docker-compose.yml down -v --remove-orphans
docker network create monitorsoft_nats || true
docker compose -f docker/docker-compose.yml up -d --build
```

Проверка:

- UI: `http://127.0.0.1:8080/`
- n8n: `http://127.0.0.1:5679/`
- список контейнеров: `docker compose -f docker/docker-compose.yml ps`

### Что менять в env

В этом режиме ничего менять не нужно. По умолчанию n8n вызывает tool proxy так:

- `TOOL_PROXY_URL=http://src_n8n:9000/tool` (это адрес внутри docker-сети, фиксирован в compose)

## 2) Вариант B: инфраструктура в Docker, сервисы запускать напрямую (IDE)

### 2.1 Поднять инфраструктуру

```bash
docker compose -f docker/docker-compose.yml up -d nats src_postgres redis n8n n8n_webhook n8n_worker src_n8n
```

Если вам нужны демо-tools:

```bash
docker compose -f docker/docker-compose.yml up -d src_api_gateway
```

### 2.2 Локальный Python env

Из корня репо:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r src_agent/requirements.txt -r src_n8n/requirements.txt -r src_llm/requirements.txt -r src_api_gateway/requirements.txt
```

### 2.3 Какие env выставить

Минимальный набор для запуска локально (в шелле или в `.env` файлов сервиса):

- `NATS_URL=nats://127.0.0.1:4222`
- `DATABASE_URL=postgresql://mcp:mcp_pass@127.0.0.1:5432/mcp`
- `USER_ID=user123` (должен совпадать с UI/stack)

### 2.4 Как запускать сервисы напрямую

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

Workflows лежат в `docker/n8n/workflows/*.json`.

Импорт:

```bash
docker compose -f docker/docker-compose.yml run --rm n8n_import
```

Важно: CLI импорт деактивирует workflows. Чтобы включить обратно, запустите activation jobs:

```bash
docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_router
docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_echo
docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_collect_name
docker compose -f docker/docker-compose.yml run --rm --no-deps n8n_activate_airports_weather
```

## 6) Быстрый smoke / E2E

Dockerized E2E runner:

```bash
docker compose -f docker/docker-compose.yml --profile test run --rm --build src_e2e
```

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

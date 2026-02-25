# src_langgraph

Минимальный orchestrator на `LangGraph`, совместимый по контракту с `src_agent`:
- вход: `N8nRunRequest` (NATS request)
- выход: `N8nRunResponse` (NATS reply)

## Что реализовано

- `echo@2.0.0`
- `where_my_flight@2.0.0` (multi-turn с `PARTIAL` + `ASK_USER_INPUT`)
- `find_nearest_airport@2.0.0` (tools + map events)
- `free_speech@2.0.0` (fallback)

## Где настраивается коннект к LLM

- `src_langgraph/settings.py`
  - `NATS_LLM_SUBJECT` (prefix, по умолчанию `nats.llm.`)
  - `USER_ID`
- Итоговый subject для LLM:
  - `f"{NATS_LLM_SUBJECT}{USER_ID}"`

LLM вызывается из `src_langgraph/service.py` в методе `_call_llm(...)`.

## Где настраивается коннект к tools

- `src_langgraph/settings.py`
  - `NATS_TOOLS_PREFIX` (по умолчанию `nats.tools.`)
- Итоговый subject:
  - `f"{NATS_TOOLS_PREFIX}{tool_name}"`

Tools вызываются из `src_langgraph/service.py` в методе `_call_tool(...)`.

## Полный цикл обработки (без UI)

1. `src_agent` отправляет `N8nRunRequest` в subject `NATS_N8N_RUN_SUBJECT`.
2. Для LangGraph-режима укажи:
   - `NATS_N8N_RUN_SUBJECT=nats.langgraph.run`
3. `src_langgraph` получает запрос, запускает `LangGraph` (`dispatch` -> сценарий).
4. Для роутинга/извлечения параметров/финального ответа `src_langgraph` делает NATS request в `src_llm`.
5. Для инструментов `src_langgraph` делает NATS request в `src_api_gateway` (`nats.tools.*`).
6. `src_langgraph` собирает `N8nRunResponse` (`status`, `result`, `client_handler`, `client_events`, `next_runtime`) и отвечает в reply subject.
7. `src_agent` сохраняет `next_runtime` в БД и публикует UI-команды/сообщения.

## Локальный запуск (docker compose)

В `docker/docker-compose.yml` сервис добавлен как профиль `langgraph`.

Запуск:

```bash
cd webrtc-komaroff/docker
docker compose --profile langgraph up -d nats src_api_gateway src_llm src_langgraph
```

## Как переключить src_agent на LangGraph

В `docker/docker-compose.yml` для `src_agent` уже добавлен env override:

```yaml
NATS_N8N_RUN_SUBJECT: ${NATS_N8N_RUN_SUBJECT:-nats.n8n.run}
```

Для переключения:

```bash
export NATS_N8N_RUN_SUBJECT=nats.langgraph.run
docker compose up -d src_agent
```


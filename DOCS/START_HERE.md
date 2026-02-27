# START_HERE

## 1) Подними стек

```bash
cd docker
docker compose --profile langgraph up -d --build
```

## 2) Открой UI

- `http://127.0.0.1:8080/`

## 3) Что происходит при сообщении пользователя

1. `src_front` -> `src_core` (`POST /core/message`)
2. `src_core` -> `src_agent` (`nats.agent.<user_id>`)
3. `src_agent` -> `src_langgraph` (`nats.workflow.run`)
4. `src_langgraph` -> `src_llm` (`nats.llm.<user_id>`)
5. `src_langgraph` -> `src_api_gateway` (`nats.tools.*`)
6. Ответ возвращается в UI через `nats.events.<user_id>`

## 4) Проверка сценариев

1. `где мой рейс`
2. `SU123`
3. `найди аэропорт`
4. `как дела`

## 5) Где менять сценарии

- `src_langgraph/config/scenarios/*.json` — промпты, tool names, схемы.
- `src_langgraph/scenarios/*.py` — логика сценариев.
- `src_langgraph/engine.py` — подключение сценария в граф.

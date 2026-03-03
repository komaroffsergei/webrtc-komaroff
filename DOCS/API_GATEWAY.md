# src_api_gateway

`src_api_gateway` предоставляет:

- HTTP endpoints под `/api/*` для фронта/ядра.
- NATS tools под `nats.tools.*` для workflow runtime.

## NATS tools

Формат: `ToolCallRequest` -> `ToolCallResponse`.

Примеры subjects:
- `nats.tools.get_current_position`
- `nats.tools.search_airports_nearby`
- `nats.tools.build_route`
- `nats.tools.get_flight_status`

## Где смотреть код

- `src_api_gateway/main.py`
- `src_api_gateway/tools/`
- `src_shared/contracts/tools.py`

## Проверка

```bash
docker compose -f docker/docker-compose.yml ps src_api_gateway nats
```

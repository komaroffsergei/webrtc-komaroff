# `src_langgraph_rb`

`src_langgraph_rb` совмещает Ruby runtime и декларативный DSL/catalog для сценариев.

Runtime обслуживает мигрированные сценарии:
- `free_speech@2.0.0`
- `where_my_flight@2.0.0`
- `find_nearest_airport@2.0.0`

NATS subjects:
- `nats.workflow.run.ruby`
- `nats.workflow.health.ruby`

Python `src_langgraph` остается отдельным runtime на:
- `nats.workflow.run.python`
- `nats.workflow.health.python`

Переключение между Python и Ruby делается только конфигурацией subject'ов у `src_agent`. Скрытого fallback между runtime нет.

## Что внутри

- NATS req-reply runtime для `WorkflowRunRequest` и health-check.
- Совместимый `WorkflowRunResponse` со статусами `DONE`, `PARTIAL`, `FAILED`.
- Stateful dialog memory: `summary`, `recent_turns`, `artifact_memory`.
- Pending-flow для `where_my_flight`.
- Map events и artifact persistence для `find_nearest_airport`.
- Декларативный built-in catalog и адаптация graph-spec в `LangGraphRB::Graph`.

## Как проходит запрос

1. [bin/service](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service) читает env через [runtime/settings.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb) и запускает [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb).
2. `Runtime::Service#run` подключается к NATS, подписывается на run/health subjects и создает `RuntimeIo` и `Engine`.
3. `Runtime::Service#handle_run` валидирует вход через [runtime/contracts/workflow.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/workflow.rb) и передает запрос в `Runtime::Engine#run`.
4. `Runtime::Engine#run` подготавливает память, выбирает сценарий, исполняет graph и возвращает `next_runtime`.
5. Сценарные узлы вызывают LLM/tools только через [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb).

## Где смотреть код

- orchestration: [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
- transport: [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
- downstream I/O: [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
- memory: [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb)
- runtime scenarios:
  - [runtime/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
  - [runtime/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
  - [runtime/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
- DSL/catalog:
  - [scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)
  - [catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/catalog.rb)
  - [adapters/lang_graph_rb/builder_plan.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb)

Краткая карта модулей: [CODEMAP.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/CODEMAP.md)

## Локальные команды

Первичная настройка:

```bash
cd src_langgraph_rb
bin/setup
```

Локальный запуск runtime:

```bash
cd src_langgraph_rb
NATS_URL=nats://localhost:4222 \
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.ruby \
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.ruby \
bin/service
```

## Как менять сценарии

1. Меняй JSON-конфиг в [config/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios), если меняются prompts, schema или tool names.
2. Меняй DSL-описание в [lib/src_langgraph_rb/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios), если меняется graph structure.
3. Меняй runtime-узлы в [lib/src_langgraph_rb/runtime/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios), если меняется исполняемое поведение.

## Текущие ограничения

- Ruby runtime не реализует `echo@2.0.0`.
- Выбор между Python и Ruby runtime не автоматический; он задается subject'ами снаружи.
- При падении внешнего LLM/tool runtime возвращает нормализованную transport error, но не лечит внешний сервис.
- DSL остается декларативным; inline router lambdas и execution blocks по-прежнему запрещены.

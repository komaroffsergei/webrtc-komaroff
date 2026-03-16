# `src_langgraph_rb`

`src_langgraph_rb` сейчас выполняет две задачи:
- дает декларативный DSL/catalog для описания сценариев;
- поднимает отдельный Ruby runtime, совместимый по контракту с `src_agent`.

Ruby runtime обслуживает только мигрированные сценарии:
- `free_speech@2.0.0`
- `where_my_flight@2.0.0`
- `find_nearest_airport@2.0.0`

Субъекты NATS у Ruby runtime:
- `nats.workflow.run.ruby`
- `nats.workflow.health.ruby`

Python `src_langgraph` остается отдельным runtime на:
- `nats.workflow.run.python`
- `nats.workflow.health.python`

Переключение между Python и Ruby делается только конфигурацией subject'ов у `src_agent` и `src_e2e`. Скрытого fallback между runtime нет.

## Что реализовано

- NATS req-reply service для `WorkflowRunRequest` и health-check.
- Совместимая форма ответа `WorkflowRunResponse` c `DONE`, `PARTIAL`, `FAILED`.
- Stateful dialog memory:
  - `summary`
  - `recent_turns`
  - `artifact_memory`
- Pending-flow для `where_my_flight`.
- Map events и artifact persistence для `find_nearest_airport`.
- Двухпроходный ответ и reference resolution для `free_speech`.
- Декларативный built-in catalog и адаптация graph-spec в `LangGraphRB::Graph`.

## Как проходит запрос

1. [bin/service](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service) читает env через [runtime/settings.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb) и запускает [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb).
2. `Runtime::Service#run` подключается к NATS, подписывается на `run_subject` и `health_subject`, создает `RuntimeIo` и `Engine`.
3. `Runtime::Service#handle_run` валидирует вход через [runtime/contracts/workflow.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/workflow.rb) и передает запрос в `Runtime::Engine#run`.
4. `Runtime::Engine#run`:
   - подготавливает память через [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb),
   - выбирает сценарий через `#initial_scenario` и [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb),
   - исполняет compiled graph нужного сценария,
   - финализирует `next_runtime`, turn ids и artifact memory в `#finalize_response`.
5. Сценарные узлы вызывают LLM/tools только через [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb).
6. `Runtime::Service#safe_respond` возвращает JSON по NATS reply subject.

## Где смотреть ключевую логику

- Главный orchestration flow: [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
  - `Engine#run`
  - `Engine#build_graphs`
  - `Engine#node_callable`
  - `Engine#router_callable`
  - `Engine#finalize_response`
- Транспорт и NATS lifecycle: [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
  - `Service#run`
  - `Service#handle_run`
  - `Service#handle_health`
- Вызовы downstream сервисов: [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
  - `RuntimeIo#call_llm`
  - `RuntimeIo#call_tool`
  - `RuntimeIo#request_json`
- Память и восстановление контекста: [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb)
  - `prepare_dialog_memory`
  - `compact_memory`
  - `build_dialog_context`
  - `append_exchange`
- `free_speech`: [runtime/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
  - `prepare_context`
  - `primary_pass`
  - `retry_pass`
  - `resolve_entity_reference`
  - `needs_knowledge_retry?` логика через `needs_knowledge_retry`
- `where_my_flight`: [runtime/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
  - `collect_params`
  - `lookup_tool`
  - `reroute`
- `find_nearest_airport`: [runtime/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
  - `prepare_search`
  - `prepare_route`
  - `build_route`
  - `normalize_route_args`

## DSL и runtime связаны, но не смешаны

Authoring-слой по-прежнему декларативный:
- built-in scenario spec собираются в [scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb);
- graph-spec описываются в [scenarios/*.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios);
- `Catalog` и `BuilderPlan` превращают spec в исполняемый `LangGraphRB::Graph`.

Исполняемое поведение при этом лежит отдельно в [runtime/scenarios/*.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios).

Это важно:
- DSL отвечает за структуру;
- runtime отвечает за transport, state, memory и side effects;
- одно и то же описание сценария можно держать reviewable и сериализуемым.

## Структура проекта

- `bin/` — локальные entrypoint'ы и quality commands.
- `config/scenarios/` — JSON-конфиги промптов, tools и router policy.
- `lib/src_langgraph_rb/contracts/` — value objects authoring-слоя.
- `lib/src_langgraph_rb/schema/` — immutable schema для graph-spec.
- `lib/src_langgraph_rb/dsl/` — builders декларативного DSL.
- `lib/src_langgraph_rb/catalog/` — сборка и lookup catalog.
- `lib/src_langgraph_rb/adapters/` — адаптация spec в `LangGraphRB`.
- `lib/src_langgraph_rb/runtime/` — NATS runtime, memory, router, scenarios.
- `lib/src_langgraph_rb/scenarios/` — built-in DSL описания сценариев.
- `spec/` — RSpec покрытие DSL, adapter и runtime.

Подробная карта по каждому файлу лежит в [CODEMAP.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/CODEMAP.md).

## Локальные команды

Первичная настройка:

```bash
cd src_langgraph_rb
bin/setup
```

Запуск RSpec:

```bash
cd src_langgraph_rb
bin/spec
```

Smoke check:

```bash
cd src_langgraph_rb
bin/smoke
```

Полная локальная проверка:

```bash
cd src_langgraph_rb
bin/check
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
4. Добавляй/обновляй тесты в [spec/runtime_spec.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_spec.rb), [spec/runtime_engine_spec.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_engine_spec.rb) и DSL/spec файлах.

## Текущие ограничения

- Ruby runtime не реализует `echo@2.0.0`.
- Выбор между Python и Ruby runtime не автоматический; он задается subject'ами снаружи.
- При падении внешнего LLM/tool runtime возвращает нормализованную transport error, но не лечит внешний сервис.
- DSL остается декларативным; inline router lambdas и execution blocks по-прежнему запрещены.

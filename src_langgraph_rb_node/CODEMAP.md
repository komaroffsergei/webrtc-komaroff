# `src_langgraph_rb_node` Code Map

Карта нового library-style runtime на `AsyncGraph`.

## Рекомендуемый порядок чтения

1. `lib/src_langgraph_rb_node/runtime/service.rb`
2. `lib/src_langgraph_rb_node/runtime/engine.rb`
3. `lib/src_langgraph_rb_node/runtime/graph_runner.rb`
4. `lib/src_langgraph_rb_node/runtime/request_executor.rb`
5. `lib/src_langgraph_rb_node/runtime/router.rb`
6. `lib/src_langgraph_rb_node/scenarios/where_my_flight.rb`
7. `lib/src_langgraph_rb_node/scenarios/find_nearest_airport.rb`
8. `lib/src_langgraph_rb_node/scenarios/free_speech.rb`
9. `lib/src_langgraph_rb_node/scenarios/built_in_registry.rb`

## Верхний уровень

| Путь | Назначение |
| --- | --- |
| `Gemfile` | bundler entrypoint |
| `src_langgraph_rb_node.gemspec` | gem metadata и зависимости |
| `README.md` | architecture, execution model, authoring style |
| `CODEMAP.md` | быстрый вход в код |
| `lib/src_langgraph_rb_node.rb` | central require graph и public API |
| `spec` | executable examples и regression tests |

## Runtime boundary

| Файл | Что смотреть |
| --- | --- |
| `runtime/service.rb` | env defaults, NATS subjects, run/health handling |
| `runtime/engine.rb` | scenario selection, direct-start, memory finalization, nested reroute |
| `runtime/router.rb` | top-level LLM router, routing entries |
| `runtime/runtime_io.rb` | `call_llm`, `call_tool`, transport normalization |
| `runtime/request_executor.rb` | `AsyncGraph::Request` -> runtime boundary |
| `runtime/graph_runner.rb` | `Graph#step` loop, `Suspended`, `Advanced`, finish merge, joins |
| `runtime/responses.rb` | `DONE`, `PARTIAL`, `FAILED` builders |
| `runtime/memory.rb` | `dialog_memory`, compaction, artifact persistence |

## Scenario registry

| Файл | Роль |
| --- | --- |
| `scenario_definition.rb` | `ScenarioMetadata`, `ScenarioDefinition` |
| `registry.rb` | in-memory scenario lookup |
| `scenarios/built_in_registry.rb` | built-in registration |

## Authoring model

Каждый сценарий это:

- metadata через `ScenarioDefinition`
- один `AsyncGraph::Graph`
- явные route-ноды через `AsyncGraph::Command.goto`
- отдельные terminal response nodes

Без hidden layers:

- нет builder DSL
- нет compute-op registry
- нет compiled graph form

## Internal request vocabulary

| kind | Где исполняется | Что означает |
| --- | --- | --- |
| `:llm` | `runtime/request_executor.rb` | LLM req-reply через `RuntimeIo#call_llm` |
| `:tool` | `runtime/request_executor.rb` | tool req-reply через `RuntimeIo#call_tool` |

## Where to patch by intent

| Нужно изменить | Файл |
| --- | --- |
| новый сценарий | `lib/src_langgraph_rb_node/scenarios/*.rb` |
| direct-start / router priority | `lib/src_langgraph_rb_node/runtime/engine.rb` |
| top-level routing prompt | `lib/src_langgraph_rb_node/runtime/router.rb` |
| внешний request kind | `lib/src_langgraph_rb_node/runtime/request_executor.rb` |
| step loop / fork-join behavior | `lib/src_langgraph_rb_node/runtime/graph_runner.rb` |
| wire contracts | `lib/src_langgraph_rb_node/runtime/contracts/*.rb` |

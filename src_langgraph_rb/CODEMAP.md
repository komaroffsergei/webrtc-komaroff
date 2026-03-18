# `src_langgraph_rb` Code Map

Рабочая карта текущего DSL-driven runtime. Этот файл нужен для быстрого входа в код и поиска точки правки. Архитектурное описание см. в [`README.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md).

## Рекомендуемый порядок чтения

1. [lib/src_langgraph_rb/runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
2. [lib/src_langgraph_rb/runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
3. [lib/src_langgraph_rb/runtime/compute_ops.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/compute_ops.rb)
4. [lib/src_langgraph_rb/runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
5. [lib/src_langgraph_rb/runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb)
6. [lib/src_langgraph_rb/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/free_speech.rb)
7. [lib/src_langgraph_rb/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/where_my_flight.rb)
8. [lib/src_langgraph_rb/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/find_nearest_airport.rb)
9. [lib/src_langgraph_rb/scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)

## Верхний уровень

| Путь | Назначение |
| --- | --- |
| [Gemfile](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile) | bundler entrypoint |
| [Gemfile.lock](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile.lock) | lock versions |
| [src_langgraph_rb.gemspec](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/src_langgraph_rb.gemspec) | gem metadata |
| [README.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md) | runtime architecture and flows |
| [lib/src_langgraph_rb.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb.rb) | central require graph и public API |
| [lib/src_langgraph_rb/errors.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb) | typed exceptions |

## Слой авторинга

| Каталог | Что внутри |
| --- | --- |
| [lib/src_langgraph_rb/contracts](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts) | validation/value objects authoring API |
| [lib/src_langgraph_rb/schema](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema) | immutable graph/schema objects |
| [lib/src_langgraph_rb/dsl](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl) | builders декларативного DSL |
| [lib/src_langgraph_rb/catalog](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/catalog) | catalog build/filter/lookup |
| [lib/src_langgraph_rb/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios) | built-in DSL descriptions и source of truth |
| [lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb) | `Scenario` -> `LangGraphRB::Graph` |

## Runtime boundary files

| Файл | Что искать внутри |
| --- | --- |
| [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) | NATS lifecycle, run/health handler, safe JSON reply |
| [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) | graph invocation, node dispatch, router dispatch, finalization |
| [runtime/compute_ops.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/compute_ops.rb) | reusable compute ops вместо scenario runtime files |
| [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb) | downstream req-reply и transport normalization |
| [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb) | LLM router по catalog metadata |
| [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb) | context shape и artifact storage |

## `kind` -> executor mapping

| `kind` | Исполняющий код |
| --- | --- |
| `compute` | [runtime/compute_ops.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/compute_ops.rb) |
| `tool_call` | `Engine#generic_tool_call` в [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) |
| `final_response` | [runtime/responses.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `state_response` | `Engine#ensure_response!` в [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) |
| `done_response` | [runtime/responses.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `failed_response` | [runtime/responses.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `partial_response` | [runtime/responses.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |

## Compute ops

| `op` | Используется в | Что делает |
| --- | --- | --- |
| `resolve_context_references` | `free_speech` | entity extraction и reference resolution |
| `compose_free_speech_response` | `free_speech` | primary/retry response generation |
| `collect_tool_params_with_pending` | `where_my_flight` | tool params + pending merge + missing/reroute |
| `tool_lookup_with_llm_response` | `where_my_flight` | tool call + not_found/error mapping + final response text |
| `reroute_selected_scenario` | `where_my_flight` | pending reroute в другой scenario graph |
| `prepare_airport_search` | `find_nearest_airport` | position -> search args |
| `prepare_airport_route` | `find_nearest_airport` | airports -> route args |
| `build_route_with_response` | `find_nearest_airport` | route tool call + final text + client events |

## Router sources

| Что влияет | Источник |
| --- | --- |
| global router prompt | [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb) |
| list of available scenarios | [scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb) |
| per-scenario router description | `routing_description` inside each scenario DSL file |

## Scenario touchpoints

| Scenario file | Важные вещи внутри |
| --- | --- |
| [scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/free_speech.rb) | free-form prompts, retry config, `compute` nodes для references и response |
| [scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/where_my_flight.rb) | flight prompts/schema, pending config, reroute flow |
| [scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/find_nearest_airport.rb) | search/route prompts, defaults, airport client events |

## Exceptions and normalization map

| Source | Исключение / ошибка | Boundary result |
| --- | --- | --- |
| [errors.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb) | `ValidationError` | normalized failed workflow at service boundary |
| [errors.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb) | `RegistryError` | normalized failed workflow at service boundary |
| [errors.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb) | `FragmentError` | authoring/build-time failure |
| [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb) | downstream timeout / invalid JSON / no responders | `llm_transport_error` or `tool_transport_error` |
| [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) | invalid request / missing session / generic `StandardError` | `WorkflowRunResponse(status=FAILED)` |
| [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) | health path failures | unhealthy response with `health_failed` |

## Where to patch by intent

| Нужно изменить | Файл/каталог |
| --- | --- |
| prompts / schema / defaults / routing hints / graph edges | [lib/src_langgraph_rb/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios) |
| compute behavior | [runtime/compute_ops.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/compute_ops.rb) |
| orchestration / node dispatch / finalization | [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) |
| router behavior | [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb) |
| transport contracts | [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb), [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb) |

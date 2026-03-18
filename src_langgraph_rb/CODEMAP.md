# `src_langgraph_rb` Code Map

Рабочая карта runtime, DSL и boundary files. Этот файл нужен для быстрого входа в код и поиска точки правки. Архитектурное описание и sequence diagrams см. в [`README.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md).

## Рекомендуемый порядок чтения

1. [lib/src_langgraph_rb/runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
2. [lib/src_langgraph_rb/runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
3. [lib/src_langgraph_rb/runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
4. [lib/src_langgraph_rb/runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb)
5. [lib/src_langgraph_rb/runtime/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
6. [lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
7. [lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
8. [lib/src_langgraph_rb/scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)

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
| [lib/src_langgraph_rb/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios) | built-in DSL descriptions |
| [lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb) | `Scenario` -> `LangGraphRB::Graph` |

## Runtime boundary files

| Файл | Точка чтения | Что искать внутри |
| --- | --- | --- |
| [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) | сначала | NATS connect, subscribe, run/health handler, reply normalization |
| [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) | сразу после service | main orchestration, node/router dispatch, finalization |
| [runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb) | после engine | downstream req-reply и transport normalization |
| [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb) | когда нужен router logic | LLM `routing_decision` |
| [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb) | когда нужен context shape | compaction и artifact storage |

## Key methods by file

### `runtime/service.rb`

| Метод | Назначение |
| --- | --- |
| [`Settings.from_env`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L26) | env -> typed runtime settings |
| [`Service.run_from_env`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L46) | единая точка входа для CLI/runtime startup |
| [`run`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L58) | bootstrap runtime и подписка на subjects |
| [`handle_run`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L107) | parsing + contract validation + engine call |
| [`invalid_run_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L117) | build safe failed response |
| [`handle_health`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L135) | health req-reply |
| [`safe_respond`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb#L156) | no-reply guard и NATS respond safety |

### `runtime/engine.rb`

| Метод | Назначение |
| --- | --- |
| [`run`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L17) | full orchestration path |
| [`choose_scenario`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L45) | thin wrapper над `Router.choose_scenario` |
| [`run_selected_scenario`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L55) | compiled graph invocation |
| [`initial_scenario`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L69) | pending-aware scenario selection |
| [`node_callable`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L90) | DSL node kind dispatch |
| [`generic_tool_call`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L148) | generic tool node helper |
| [`router_callable`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L177) | DSL router dispatch |
| [`finalize_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L201) | memory + artifact persistence + turn ids |
| [`with_artifact_memory`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L246) | `client_events` -> `artifact_memory` |

### `runtime/runtime_io.rb`

| Метод | Назначение |
| --- | --- |
| [`call_llm`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb#L19) | LLM req-reply boundary |
| [`call_tool`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb#L33) | tool req-reply boundary |
| [`request_json`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb#L60) | parse and verify JSON object response |

### `runtime/router.rb`

| Метод | Назначение |
| --- | --- |
| [`choose_scenario`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb#L31) | central router call |
| [`filtered_scenarios`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb#L54) | exclusion-aware scenario list |

## `kind` -> method mapping

| `kind` | Исполняющий код |
| --- | --- |
| `context_enrichment` | [`FreeSpeech.prepare_context`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb#L53) |
| `free_speech_primary` | [`FreeSpeech.primary_pass`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb#L73) |
| `free_speech_retry` | [`FreeSpeech.retry_pass`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb#L112) |
| `flight_collect_params` | [`WhereMyFlight.collect_params`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb#L44) |
| `flight_lookup_tool` | [`WhereMyFlight.lookup_tool`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb#L114) |
| `flight_reroute` | [`WhereMyFlight.reroute`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb#L156) |
| `airport_prepare_search` | [`FindNearestAirport.prepare_search`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb#L57) |
| `airport_prepare_route` | [`FindNearestAirport.prepare_route`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb#L88) |
| `airport_build_route` | [`FindNearestAirport.build_route`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb#L117) |
| `tool_call` | [`Engine#generic_tool_call`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L148) |
| `final_response` | [`Runtime::Responses.done_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `state_response` | [`Engine#ensure_response!`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb#L173) |
| `done_response` | [`Runtime::Responses.done_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `failed_response` | [`Runtime::Responses.failed_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |
| `partial_response` | [`Runtime::Responses.partial_response`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb) |

## `router` -> state mapping

| `router` id | State source |
| --- | --- |
| `free_speech_entry` | `state[:free_speech_entry]` |
| `free_speech_primary_result` | `state[:free_speech_primary_result]` |
| `flight_param_status` | `state[:flight_param_status]` |
| `flight_tool_result_status` | `state[:flight_tool_result_status]` |
| `tool_status` | derived from `state[:last_tool_ok]` |
| `route_args_status` | `state[:route_args_status]` |
| `airport_route_result_status` | `state[:airport_route_result_status]` |

## Scenario touchpoints

| Scenario | LLM calls | Tool calls | Runtime-specific side effects |
| --- | --- | --- | --- |
| `free_speech` | `routing_decision`, `final_response`, `final_response retry` | none | entity resolution from `artifact_memory` |
| `where_my_flight` | `tool_params`, `final_response` | `get_flight_status` | pending flow, possible reroute |
| `find_nearest_airport` | `tool_params search`, `tool_params route`, `final_response` | `get_current_position`, `search_airports_nearby`, `build_route` | emits `SET_POSITION`, `SET_AIRPORTS`, `BUILD_ROUTE` |

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
| env / subjects / timeouts | [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) |
| NATS boundary behavior | [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb) |
| orchestration / node routing / finalization | [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb) |
| router policy | [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb), [config/scenarios/router.json](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/router.json) |
| prompts / tool schema | [config/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios) |
| executable scenario behavior | [runtime/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios) |
| DSL graph structure | [lib/src_langgraph_rb/scenarios](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios) |
| graph compilation adapter | [adapters/lang_graph_rb/builder_plan.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb) |

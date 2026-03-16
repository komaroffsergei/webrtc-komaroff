# `src_langgraph_rb` Code Map

Этот документ нужен для быстрого входа в Ruby runtime без чтения всего дерева подряд.
Формат одинаковый:
- путь к файлу;
- что файл делает;
- на какие классы/методы смотреть в первую очередь.

## Рекомендуемый порядок чтения

1. [bin/service](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service)
2. [lib/src_langgraph_rb/runtime/settings.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb)
3. [lib/src_langgraph_rb/runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
4. [lib/src_langgraph_rb/runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
5. [lib/src_langgraph_rb/runtime/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
6. [lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
7. [lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
8. [lib/src_langgraph_rb/scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)
9. [lib/src_langgraph_rb/scenarios/*.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios)
10. [spec/runtime_spec.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_spec.rb) и [spec/runtime_engine_spec.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_engine_spec.rb)

## Верхний уровень проекта

- [`.rspec`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/.rspec)
  Запускает RSpec с проектным `spec_helper`.

- [`Gemfile`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile)
  Ruby dependencies для runtime, DSL и тестов.

- [`Gemfile.lock`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile.lock)
  Зафиксированные версии gem dependencies.

- [`README.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md)
  Актуальное high-level описание сервиса, его subject'ов и архитектуры.

- [`CODEMAP.md`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/CODEMAP.md)
  Этот file-by-file обзор.

- [`Rakefile`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Rakefile)
  Локальные quality tasks.
  Ключевые точки: `task :syntax`, `task :smoke`, `task :spec`, `task :check`.

- [`src_langgraph_rb.gemspec`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/src_langgraph_rb.gemspec)
  Gem metadata и packaged files.
  Смотреть: `spec.files`, `spec.add_dependency`, `spec.summary`, `spec.description`.

## `bin/`

- [`bin/check`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/check)
  Shortcut к `bundle exec rake check`.

- [`bin/run`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/run)
  Альтернативный entrypoint запуска runtime.
  Смотреть: создание `SrcLanggraphRb::Runtime::Service`.

- [`bin/service`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service)
  Канонический runtime entrypoint.
  Смотреть: `Settings.from_env`, `Service.new(...).run`.

- [`bin/setup`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/setup)
  `bundle install`.

- [`bin/smoke`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/smoke)
  Shortcut к `bundle exec rake smoke`.

- [`bin/spec`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/spec)
  Shortcut к `bundle exec rspec`.

## `config/scenarios/`

- [`config/scenarios/router.json`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/router.json)
  Router policy: task prompt и список доступных сценариев для `routing_decision`.
  Используется в `Runtime::Router::CFG`.

- [`config/scenarios/free_speech.json`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/free_speech.json)
  Prompt blocks для `free_speech`.
  Используется в `Runtime::Scenarios::FreeSpeech::CFG`.

- [`config/scenarios/where_my_flight.json`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/where_my_flight.json)
  Prompts, tool names и schema для flight lookup.
  Используется в `Runtime::Scenarios::WhereMyFlight::CFG`.

- [`config/scenarios/find_nearest_airport.json`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/find_nearest_airport.json)
  Prompts, defaults, schema и tools для nearest-airport flow.
  Используется в `Runtime::Scenarios::FindNearestAirport::CFG`.

## `lib/src_langgraph_rb.rb` и общие файлы

- [`lib/src_langgraph_rb.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb.rb)
  Центральный require graph всего gem.
  Внешний API: `SrcLanggraphRb.build_catalog`, `SrcLanggraphRb.built_in_catalog`.

- [`lib/src_langgraph_rb/version.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/version.rb)
  Версия gem/runtime.

- [`lib/src_langgraph_rb/errors.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb)
  Базовые исключения: `Error`, `ValidationError`, `RegistryError`, `FragmentError`.

## Authoring contracts

- [`lib/src_langgraph_rb/contracts/common.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts/common.rb)
  Immutable envelope/value objects общего назначения.
  Смотреть: `TraceEnvelope`, `ServiceHealthRequest`, `ServiceHealthResponse`, `ErrorInfo`.

- [`lib/src_langgraph_rb/contracts/workflow.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts/workflow.rb)
  Authoring-side классы `WorkflowRuntimeState`, `WorkflowRunRequest`, `WorkflowRunResponse`.
  Смотреть: `.from_h`, `#to_h`, `#with`.

- [`lib/src_langgraph_rb/contracts/llm.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts/llm.rb)
  Authoring-side `LlmRequest` и `LlmResponse`.

- [`lib/src_langgraph_rb/contracts/tools.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts/tools.rb)
  Authoring-side tool envelope classes.

- [`lib/src_langgraph_rb/contracts/validation.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts/validation.rb)
  Primitive validators для authoring-side value objects.
  Смотреть: `hash!`, `string!`, `uuid!`, `integer!`, `deep_copy_hash`.

## Schema layer

- [`lib/src_langgraph_rb/schema/node.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/node.rb)
  Immutable node spec, `#to_h`.

- [`lib/src_langgraph_rb/schema/edge.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/edge.rb)
  Edge spec.
  Смотреть: `#direct?`, `#conditional?`, `#to_h`.

- [`lib/src_langgraph_rb/schema/fragment_import.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/fragment_import.rb)
  Модель imported fragment alias'а.

- [`lib/src_langgraph_rb/schema/fragment.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/fragment.rb)
  Fragment spec.
  Смотреть: `#validate!`, `#to_h`.

- [`lib/src_langgraph_rb/schema/graph.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/graph.rb)
  Graph spec: `entry_point`, `finish_points`, `nodes`, `edges`, `defaults`, `imports`.

- [`lib/src_langgraph_rb/schema/scenario_metadata.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/scenario_metadata.rb)
  Metadata сценария: title, description, tags, capabilities, required_tools, runtime_flags.

- [`lib/src_langgraph_rb/schema/scenario.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema/scenario.rb)
  Полный scenario spec.
  Смотреть: `#validate!`, `#to_h`.

## Validation

- [`lib/src_langgraph_rb/validation/rules.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/validation/rules.rb)
  Основные structural rules для DSL/spec.
  Ключевые методы:
  - `validate_scenario!`
  - `validate_fragment!`
  - `validate_graph!`
  - `validate_edges!`
  - `ensure_unique_ids!`

## DSL

- [`lib/src_langgraph_rb/dsl/support/identifiers.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/support/identifiers.rb)
  Нормализация node/router id и namespacing imported fragments.
  Смотреть: `normalize_id`, `normalize_router`, `namespaced_id`.

- [`lib/src_langgraph_rb/dsl/support/normalization.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/support/normalization.rb)
  Нормализация DSL data values.

- [`lib/src_langgraph_rb/dsl/support/fragment_importer.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/support/fragment_importer.rb)
  Импорт fragment в graph builder с alias namespace.
  Это место, где `use ... as:` превращается в реальные node/edge ids.

- [`lib/src_langgraph_rb/dsl/fragment_builder.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/fragment_builder.rb)
  Builder для fragment spec.
  Ключевые методы: `.build`, `#node`, `#edge`, `#conditional_edge`, `#finish_point`, `#build`.

- [`lib/src_langgraph_rb/dsl/graph_builder.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/graph_builder.rb)
  Builder верхнего graph spec.
  Ключевые методы:
  - `#entry_point`
  - `#use`
  - `#ref`
  - `#register_import`
  - `#build`

- [`lib/src_langgraph_rb/dsl/scenario_builder.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl/scenario_builder.rb)
  Builder целого scenario spec.
  Ключевые методы:
  - `.build`
  - `#title`
  - `#description`
  - `#tags`
  - `#capabilities`
  - `#required_tools`
  - `#runtime_flags`
  - `#graph`
  - `#build`

## Catalog и adapter

- [`lib/src_langgraph_rb/catalog.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/catalog.rb)
  Immutable catalog контейнер.
  Смотреть:
  - `.build`
  - `#fetch`
  - `#all`
  - `#filter`
  - `#to_builder_plan`

- [`lib/src_langgraph_rb/catalog/builder.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/catalog/builder.rb)
  Сборщик catalog из DSL blocks.
  Смотреть: `.build`, `#fragment`, `#scenario`, `#build`, `#fetch_fragment`.

- [`lib/src_langgraph_rb/compat/langgraph_rb_loader.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/compat/langgraph_rb_loader.rb)
  Изолированный loader внешнего `langgraph_rb`.
  Ключевая задача: тянуть только нужные graph primitives и не размазывать внешний API по проекту.

- [`lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb)
  Превращает `Scenario` в список builder instructions и затем в `LangGraphRB::Graph`.
  Смотреть:
  - `.from_spec`
  - `.build_edge_instructions`
  - `#to_builder_block`
  - `#build_graph`

## Built-in DSL сценарии

- [`lib/src_langgraph_rb/scenarios/shared_fragments.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/shared_fragments.rb)
  Общие graph fragments, переиспользуемые разными сценариями.
  Именно здесь объявлены типовые terminal/final tails.

- [`lib/src_langgraph_rb/scenarios/free_speech.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/free_speech.rb)
  DSL graph-spec для `free_speech`.
  Смотреть: `register(builder)`, `conditional_edge :prepare_context`, `conditional_edge :compose_primary`.

- [`lib/src_langgraph_rb/scenarios/where_my_flight.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/where_my_flight.rb)
  DSL graph-spec flight сценария.
  Смотреть `conditional_edge :collect_params` и переходы `ready/missing/reroute`.

- [`lib/src_langgraph_rb/scenarios/find_nearest_airport.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/find_nearest_airport.rb)
  DSL graph-spec airport сценария.
  Смотреть ветки `tool_status`, `route_args_status`, `airport_route_result_status`.

- [`lib/src_langgraph_rb/scenarios/built_in_catalog.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)
  Точка сборки shipped catalog.
  Смотреть: `build`, порядок регистрации `SharedFragments`, `FreeSpeech`, `WhereMyFlight`, `FindNearestAirport`.

## Runtime shared files

- [`lib/src_langgraph_rb/runtime/settings.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb)
  Runtime settings из env.
  Смотреть:
  - `.from_env`
  - env keys `NATS_WORKFLOW_RUN_SUBJECT`, `NATS_WORKFLOW_HEALTH_SUBJECT`, `NATS_REQUEST_TIMEOUT_SECONDS`

- [`lib/src_langgraph_rb/runtime/util.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/util.rb)
  Базовые helpers для runtime.
  Ключевые методы:
  - `deep_symbolize`
  - `deep_stringify`
  - `extract_hash`
  - `text`
  - `integer`
  - `float`
  - `generate_uuid`

- [`lib/src_langgraph_rb/runtime/state.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/state.rb)
  Константы поддерживаемых сценариев в runtime.
  Используется как компактный registry.

- [`lib/src_langgraph_rb/runtime/scenario_ids.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenario_ids.rb)
  Канонические id сценариев для runtime router/engine.

- [`lib/src_langgraph_rb/runtime/config_loader.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/config_loader.rb)
  Loader JSON-конфигов.
  Смотреть:
  - `load_config`
  - `text_block`
  - `dict_value`
  - `list_of_dicts`

- [`lib/src_langgraph_rb/runtime/responses.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/responses.rb)
  Единые конструкторы ответов.
  Смотреть:
  - `next_runtime`
  - `done_response`
  - `partial_response`
  - `failed_response`

- [`lib/src_langgraph_rb/runtime/memory.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb)
  Dialog memory и context compaction.
  Ключевые методы:
  - `memory_from_context`
  - `prepare_dialog_memory`
  - `apply_edit_rewrite`
  - `compact_memory`
  - `build_dialog_context`
  - `append_exchange`
  - `response_message_text`
  - `artifact_context_block`

- [`lib/src_langgraph_rb/runtime/router.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb)
  LLM-based routing между тремя сценариями.
  Смотреть:
  - `choose_scenario`
  - `filtered_scenarios`
  - константы `ROUTER_TASK`, `ROUTER_SCENARIOS`

- [`lib/src_langgraph_rb/runtime/runtime_io.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
  Транспортный слой req-reply к `src_llm` и `src_api_gateway`.
  Ключевые методы:
  - `#call_llm`
  - `#call_tool`
  - `#request_json`
  - `#fallback_request`

- [`lib/src_langgraph_rb/runtime/engine.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
  Сердце runtime.
  Ключевые методы:
  - `#run`
  - `#initial_scenario`
  - `#build_graphs`
  - `#node_callable`
  - `#router_callable`
  - `#generic_tool_call`
  - `#run_selected_scenario`
  - `#finalize_response`
  - `#with_turn_ids`
  - `#with_artifact_memory`

- [`lib/src_langgraph_rb/runtime/service.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
  NATS lifecycle и wire contract входа/выхода.
  Смотреть:
  - `#run`
  - `#trap_signals`
  - `#handle_run`
  - `#invalid_run_response`
  - `#handle_health`
  - `#safe_respond`

## Runtime contracts

- [`lib/src_langgraph_rb/runtime/contracts/common.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/common.rb)
  Проверка trace envelope и health request.
  Смотреть:
  - `validate_trace_envelope!`
  - `validate_health_request!`
  - `error_info`

- [`lib/src_langgraph_rb/runtime/contracts/workflow.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/workflow.rb)
  Нормализация `WorkflowRunRequest` и сборка `WorkflowRunResponse`.
  Смотреть:
  - `validate_run_request!`
  - `normalize_runtime`
  - `response`

- [`lib/src_langgraph_rb/runtime/contracts/llm.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/llm.rb)
  LLM transport contract.
  Смотреть:
  - `request`
  - `normalize_response`
  - `error_response`

- [`lib/src_langgraph_rb/runtime/contracts/tools.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts/tools.rb)
  Tool transport contract.
  Смотреть:
  - `request`
  - `normalize_response`
  - `error_response`

## Runtime scenarios

- [`lib/src_langgraph_rb/runtime/scenarios/common.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/common.rb)
  Общие helpers для runtime-сценариев.
  Смотреть:
  - `extract_llm_text`
  - `normalize_tool_params`
  - `merge_non_empty_params`
  - `extract_nested_data`

- [`lib/src_langgraph_rb/runtime/scenarios/free_speech.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
  Самый сложный runtime сценарий.
  Ключевые методы:
  - `prepare_context`
  - `primary_pass`
  - `retry_pass`
  - `extract_entities_from_artifacts`
  - `resolve_entity_reference`
  - `clarify_entity_message`
  - `response_quality_score`
  - `needs_knowledge_retry`
  - `retry_reason`
  - `retry_context_artifacts`

- [`lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
  Pending scenario с переходом в reroute.
  Ключевые методы:
  - `collect_params`
  - `pending_state`
  - `lookup_tool`
  - `reroute`
  - `format_flight_message`

- [`lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
  Tool chain для гео-сценария.
  Ключевые методы:
  - `prepare_search`
  - `prepare_route`
  - `build_route`
  - `normalize_route_args`

## Specs

- [`spec/spec_helper.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/spec_helper.rb)
  Общая настройка RSpec.

- [`spec/catalog_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/catalog_spec.rb)
  Проверяет публичный API catalog.

- [`spec/built_in_catalog_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/built_in_catalog_spec.rb)
  Проверяет shipped catalog и список встроенных сценариев.

- [`spec/graph_dsl_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/graph_dsl_spec.rb)
  Проверяет DSL imports, alias resolution и `ref(...)`.

- [`spec/validation_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/validation_spec.rb)
  Проверяет structural validation rules.

- [`spec/builder_plan_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/builder_plan_spec.rb)
  Проверяет преобразование spec в `BuilderPlan` и uncompiled graph.

- [`spec/runtime_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_spec.rb)
  Интеграционные runtime проверки без реального NATS/LLM.
  Ключевые кейсы:
  - router fallback в `free_speech`
  - pending reroute для `where_my_flight`
  - `not_found` в flight lookup
  - ambiguous entity clarification
  - transport normalization в `RuntimeIo`

- [`spec/runtime_engine_spec.rb`](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/spec/runtime_engine_spec.rb)
  Проверяет `Runtime::Engine` end-to-end на fake IO.
  Ключевые кейсы:
  - `free_speech` happy path
  - `where_my_flight` partial path
  - `find_nearest_airport` с map events

## Куда идти за типовой задачей

- Проблема в запуске сервиса: [runtime/settings.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb) -> [runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
- Проблема в выборе сценария: [runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb) -> [runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
- Проблема в памяти/контексте: [runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb)
- Проблема в prompt/schema/tool binding: `config/scenarios/*.json` + соответствующий файл в `runtime/scenarios/*.rb`
- Проблема в graph structure: `lib/src_langgraph_rb/scenarios/*.rb`
- Проблема в DSL/build plan: `dsl/*` + `catalog/*` + `adapters/lang_graph_rb/builder_plan.rb`

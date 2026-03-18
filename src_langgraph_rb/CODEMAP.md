# `src_langgraph_rb` Code Map

Короткая карта актуального дерева без тестового контура.

## Рекомендуемый порядок чтения

1. [bin/service](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service)
2. [lib/src_langgraph_rb/runtime/settings.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/settings.rb)
3. [lib/src_langgraph_rb/runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
4. [lib/src_langgraph_rb/runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
5. [lib/src_langgraph_rb/runtime/scenarios/free_speech.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/free_speech.rb)
6. [lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/where_my_flight.rb)
7. [lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios/find_nearest_airport.rb)
8. [lib/src_langgraph_rb/scenarios/built_in_catalog.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios/built_in_catalog.rb)

## Верхний уровень

- [Gemfile](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile)
  Bundler entrypoint, тянет зависимости из gemspec.

- [Gemfile.lock](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/Gemfile.lock)
  Зафиксированные версии gems.

- [README.md](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/README.md)
  High-level описание runtime, subjects и структуры.

- [src_langgraph_rb.gemspec](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/src_langgraph_rb.gemspec)
  Gem metadata и packaged files.

## `bin/`

- [bin/service](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/service)
  Канонический runtime entrypoint.

- [bin/setup](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/bin/setup)
  `bundle install`.

## `config/scenarios/`

- [config/scenarios/router.json](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/router.json)
  Router policy и allowlist сценариев.

- [config/scenarios/free_speech.json](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/free_speech.json)
  Prompt blocks для `free_speech`.

- [config/scenarios/where_my_flight.json](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/where_my_flight.json)
  Prompts, tools и schema для flight lookup.

- [config/scenarios/find_nearest_airport.json](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/config/scenarios/find_nearest_airport.json)
  Prompts, defaults, schema и tools для nearest-airport flow.

## `lib/src_langgraph_rb.rb` и общие файлы

- [lib/src_langgraph_rb.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb.rb)
  Центральный require graph gem-а и внешний API `SrcLanggraphRb.build_catalog` / `SrcLanggraphRb.built_in_catalog`.

- [lib/src_langgraph_rb/version.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/version.rb)
  Версия gem/runtime.

- [lib/src_langgraph_rb/errors.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/errors.rb)
  Базовые исключения DSL/runtime слоя.

## Authoring слой

- [lib/src_langgraph_rb/contracts/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/contracts)
  Value objects и validators для authoring API.

- [lib/src_langgraph_rb/schema/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/schema)
  Immutable schema для graph/spec layers.

- [lib/src_langgraph_rb/dsl/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/dsl)
  Builders декларативного DSL.

- [lib/src_langgraph_rb/catalog/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/catalog)
  Сборка, lookup и фильтрация catalog.

- [lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/adapters/lang_graph_rb/builder_plan.rb)
  Трансляция `Scenario` в `LangGraphRB::Graph`.

- [lib/src_langgraph_rb/scenarios/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/scenarios)
  Built-in DSL описания сценариев.

## Runtime слой

- [lib/src_langgraph_rb/runtime/service.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/service.rb)
  NATS lifecycle, run/health handlers и safe JSON response.

- [lib/src_langgraph_rb/runtime/engine.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/engine.rb)
  Главный orchestration flow, выбор сценария и finalization.

- [lib/src_langgraph_rb/runtime/runtime_io.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/runtime_io.rb)
  Вызовы LLM и tools.

- [lib/src_langgraph_rb/runtime/memory.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/memory.rb)
  Dialog memory, compaction и artifact storage.

- [lib/src_langgraph_rb/runtime/router.rb](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/router.rb)
  Scenario routing поверх LLM router prompt.

- [lib/src_langgraph_rb/runtime/contracts/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/contracts)
  Runtime wire contracts для workflow, llm и tools.

- [lib/src_langgraph_rb/runtime/scenarios/](/home/komaroff/dev/monitorsoft/voice-chat/webrtc-komaroff/src_langgraph_rb/lib/src_langgraph_rb/runtime/scenarios)
  Исполняемая логика `free_speech`, `where_my_flight`, `find_nearest_airport`.

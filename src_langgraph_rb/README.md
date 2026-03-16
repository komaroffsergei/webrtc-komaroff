# `src_langgraph_rb`

`src_langgraph_rb` — Ruby runtime для мигрированных сценариев `src_langgraph` и DSL для их декларативного описания в виде переиспользуемых graph-spec.

Сейчас проект покрывает две роли:
- authoring/catalog слой для graph-spec и adapter plan
- отдельный NATS runtime sidecar на Ruby для сценариев:
  - `free_speech@2.0.0`
  - `where_my_flight@2.0.0`
  - `find_nearest_airport@2.0.0`

Runtime слушает отдельные subject'ы:
- `nats.workflow.run.ruby`
- `nats.workflow.health.ruby`

Python `src_langgraph` остаётся отдельным legacy runtime на:
- `nats.workflow.run.python`
- `nats.workflow.health.python`

Переключение между Python и Ruby выполняется только через конфигурацию subject'ов в `src_agent`/`src_e2e`; скрытого fallback между runtime нет.

## Зачем это нужно

Текущий Python `src_langgraph` совмещает сразу несколько зон ответственности:
- transport и orchestration
- runtime state и context handling
- routing по сценариям
- business flow конкретного сценария
- формирование ответа

Прямая перепись всего этого на Ruby одним шагом рискованна.

`src_langgraph_rb` сначала фиксирует только один слой: **форму сценария**.
Это дает:
- стабильную authoring-модель до появления Ruby runtime
- понятную границу между описанием сценария и его выполнением
- возможность ревьюить сценарий как структуру, а не как кусок императивного кода
- контролируемую будущую миграцию к sidecar service

## Почему API выглядит именно так

### Почему `Catalog.build`

Ранний прототип опирался на глобальный mutable registry и top-level helpers.
Для спайка это удобно, но у такого подхода есть системные проблемы:
- есть скрытое состояние
- тесты становятся менее предсказуемыми
- сложнее собирать разные наборы сценариев
- harder to reason about lifecycle and ownership

Поэтому канонический вход теперь явный:

```ruby
catalog = SrcLanggraphRb.build_catalog do
  fragment :assistant_reply_tail do
    node :respond, kind: :final_response, response_channel: :chat
    finish_point :respond
  end

  scenario "free_speech@2.0.0" do
    title "Free Speech"
    description "Generic free-form dialog without tools"
    tags :chat, :fallback
    capabilities :stateful_dialog, :final_response

    graph do
      use :assistant_reply_tail, as: :final
      entry_point :prepare_context

      node :prepare_context, kind: :context_enrichment, inputs: %i[dialog_context artifacts]
      node :compose_prompt, kind: :llm_prompt, mode: :final_response

      edge :prepare_context, :compose_prompt
      edge :compose_prompt, ref(:final, :respond)
    end
  end
end
```

Почему это лучше:
- каталог создается явно и после сборки становится неизменяемым
- нет скрытой глобальной регистрации
- built-in и custom сценарии описываются одинаково
- тестовая конфигурация локальна и детерминирована
- проще позже подменить built-in catalog на runtime-specific набор

### Почему DSL декларативный, а не исполняемый

DSL хранит **spec**, а не runtime behavior.

Пример node declaration:

```ruby
node :compose_prompt, kind: :llm_prompt, mode: :final_response
```

Node описывается метаданными, а не исполняемым блоком.
Это сделано специально.

Почему не inline lambdas в DSL:
- они слишком рано смешивают authoring и runtime
- их сложно сериализовать и анализировать
- они хуже диффуются и ревьюятся
- они мешают reuse
- они размывают контракт между DSL, runtime и adapter layer

Текущее правило жесткое:
- inline router lambdas запрещены
- graph spec должен оставаться inspectable и serializable

### Почему `use ... as:` и `ref(...)`

Переиспользование subgraph в DSL должно быть явным.
Поэтому fragment импортируется так:

```ruby
use :assistant_reply_tail, as: :final
edge :compose_prompt, ref(:final, :respond)
```

Почему не raw namespacing вроде `final__respond` прямо в authoring-коде:
- автор не должен вручную собирать технические имена
- alias импортированного fragment должен быть виден явно
- namespace rules должны жить в одном месте, а не дублироваться по сценариям
- такой API безопаснее для будущего рефакторинга fragments

`ref(:final, :respond)` — это не украшение синтаксиса, а способ централизовать resolution imported nodes.

## Анатомия сценария

### 1. Metadata

Metadata описывают смысл сценария, а не его исполнение:

```ruby
title "Where My Flight"
description "Collect flight lookup params and shape the follow-up response"
tags :flight, :lookup
capabilities :pending_params, :tool_params, :tool_call, :handoff
required_tools :get_flight_status
runtime_flags pending_key: :flight_lookup, active_workflow_id: "where_my_flight@2.0.0"
```

Metadata нужны для:
- discovery в catalog
- фильтрации сценариев
- будущих runtime policies
- формирования интеграционных контрактов

### 2. Graph

У каждого graph spec обязательно должны быть:
- один `entry_point`
- хотя бы один `finish_point`
- уникальные `node id`
- валидные targets у всех edges

Graph в DSL — это именно structure contract.
Он не должен содержать transport-specific details.

### 3. Nodes

Node описывается через `id`, `kind`, `config` и optional `meta`:

```ruby
node :collect_params, kind: :llm_tool_params, tool_name: :get_flight_status
node :ask_missing, kind: :partial_response, pending_key: :flight_lookup
node :reroute, kind: :scenario_handoff
```

`kind` — главный контракт между authoring-слоем и будущим runtime.
Именно runtime потом решит, что значит `:llm_tool_params`, `:tool_call` или `:final_response`.

Это лучше, чем сразу зашивать execution code в DSL, потому что:
- один и тот же spec можно будет маппить на разные runtime implementations
- authoring остается чистым и reviewable
- легче добавлять validation rules

### 4. Direct edges

Если переход безусловный, нужен обычный `edge`:

```ruby
edge :prepare_context, :compose_prompt
```

Здесь нет дополнительной магии: это просто направленная связь между двумя узлами.

### 5. Conditional edges

Если переход зависит от результата маршрутизации, используется `conditional_edge`:

```ruby
conditional_edge :collect_params, :flight_param_status, {
  "ready" => :call_status_tool,
  "missing" => :ask_missing,
  "reroute" => :reroute
}
```

Почему здесь router задается символическим ключом, а не кодом:
- router key стабилен и сериализуем
- diff проще читать
- runtime может связать этот key с исполняемой функцией позже
- DSL не начинает зависеть от конкретной execution environment

### 6. Fragments

Fragments — это переиспользуемые куски graph structure:

```ruby
fragment :assistant_reply_tail do
  node :respond, kind: :final_response, response_channel: :chat
  finish_point :respond
end
```

Их имеет смысл использовать там, где повторяется конец сценария, типовой handoff или общий кусок flow.

Важно:
- fragment описывает структуру
- fragment не знает, где именно он будет импортирован
- конкретный namespace определяется alias при `use`

## Что сейчас входит в built-in catalog

Сейчас библиотека поставляет built-in catalog:

```ruby
catalog = SrcLanggraphRb.built_in_catalog
catalog.all.map(&:id)
# => [
#      "find_nearest_airport@2.0.0",
#      "free_speech@2.0.0",
#      "where_my_flight@2.0.0"
#    ]
```

Built-in definitions разнесены по ответственности:
- shared fragments
- free speech
- where-my-flight
- nearest-airport
- маленький loader, который собирает built-in catalog

Это соответствует текущим правилам проекта:
- один helper — одна ответственность
- не делать monolith builder file
- не смешивать built-in catalog assembly и содержание сценариев

## Adapter к `langgraph_rb`

Adapter layer переводит `Scenario` в builder plan:

```ruby
scenario = catalog.fetch("free_speech@2.0.0")
plan = catalog.to_builder_plan(scenario.id)
graph = plan.build_graph
```

Важно понимать текущую границу:
- `build_graph` создает `LangGraphRB::Graph`
- `build_graph` **не** вызывает `compile!`
- `build_graph` **не** запускает выполнение

Это сделано намеренно.

На этом этапе нам нужен authoring layer, а не execution runtime.
Если сейчас смешать оба слоя, то DSL быстро обрастет runtime-деталями и потеряет ценность как стабильный spec format.

## Почему нет прямого `require "langgraph_rb"`

Upstream gem сейчас подтягивает больше зависимостей, чем нужно authoring-слою.
Чтобы не тащить лишние runtime concerns, compatibility layer загружает только минимально нужные graph primitives:
- `state`
- `node`
- `edge`
- `graph`

Эта изоляция лежит в compatibility-файле, а не в business DSL code.

Такое разделение лучше потому, что:
- нестабильности внешнего gem не расползаются по DSL-коду
- adapter слой остается локализованным
- потом проще заменить или расширить integration strategy

## Структура проекта

Ключевые зоны ответственности:
- `lib/src_langgraph_rb/schema/` — immutable value objects для spec model
- `lib/src_langgraph_rb/dsl/` — builders и helpers DSL authoring layer
- `lib/src_langgraph_rb/validation/` — validation rules
- `lib/src_langgraph_rb/catalog/` — сборка и доступ к catalog
- `lib/src_langgraph_rb/scenarios/` — built-in fragments и сценарии
- `lib/src_langgraph_rb/adapters/` — перевод spec в adapter plan
- `lib/src_langgraph_rb/compat/` — изолированный слой совместимости с внешними библиотеками

Это разделение выбрано потому, что оно отделяет:
- data model
- authoring API
- validation
- external integration

Именно так проще удерживать код компактным и predictable.

## Как добавить новый сценарий

1. Определить, какие fragments уже существуют и что можно переиспользовать.
2. Если общего fragment нет, добавить его в `lib/src_langgraph_rb/scenarios/`.
3. Создать новый scenario module с `register(builder)`.
4. Описать metadata и graph declaratively.
5. Подключить сценарий в built-in catalog loader, если он должен входить в shipped catalog.
6. Добавить тесты минимум на:
- graph validity
- fragment imports
- builder plan translation

## Локальные команды

Первичная настройка:

```bash
cd src_langgraph_rb
bin/setup
```

Запуск тестов:

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

Эквивалент через Rake:

```bash
cd src_langgraph_rb
bundle exec rake check
```

## IntelliJ IDEA

Для репозитория зафиксированы shared run configurations в `.run/`:
- `src_langgraph_rb setup`
- `src_langgraph_rb spec`
- `src_langgraph_rb smoke`
- `src_langgraph_rb check`

Подход выбран такой:
- не коммитить machine-specific `.idea` Ruby SDK settings
- держать в репозитории только воспроизводимые run-конфиги
- локальную привязку Ruby SDK сделать один раз в IDEA

Что нужно сделать локально в IDEA:
1. Убедиться, что установлен Ruby plugin.
2. Добавить локальный Ruby SDK, совместимый с проектом.
3. Открыть shared configs из `.run/`.
4. При необходимости пометить `src_langgraph_rb/lib` как Sources Root, а `src_langgraph_rb/spec` как Test Sources Root.

Почему не `.idea`:
- `.idea` содержит machine-specific state
- такой state плохо переносится между разработчиками
- shared `.run` лучше подходит для командной работы

## Что проверено

В проекте уже проверено:
- syntax check для `lib`, `spec`, `bin`, `Rakefile`
- smoke test для built-in catalog и adapter plan
- RSpec suite
- сохранение graph в uncompiled state

## Ограничения текущего этапа

Сейчас `src_langgraph_rb`:
- не является NATS service
- не исполняет сценарии
- не реализует runtime storage
- не решает orchestration
- не заменяет текущий Python `src_langgraph`

Это осознанное ограничение.

Сначала фиксируется authoring model.
Потом поверх нее уже можно безопасно строить Ruby sidecar runtime.

## Почему это решение лучше альтернатив на текущем этапе

По сравнению с immediate rewrite runtime на Ruby этот подход лучше, потому что:
- уменьшает риск
- отделяет моделирование сценариев от transport/runtime
- дает стабильный DSL до интеграции с NATS/LLM/tools
- упрощает ревью, тестирование и reuse

По сравнению с полностью императивным DSL этот подход лучше, потому что:
- сценарии проще валидировать
- их проще сериализовать
- их проще адаптировать к нескольким runtime implementations
- меньше скрытых связей и побочных эффектов

Именно поэтому текущая версия deliberately ограничена описанием сценариев и adapter-ready builder plan.

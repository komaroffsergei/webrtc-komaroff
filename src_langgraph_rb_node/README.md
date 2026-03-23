# `src_langgraph_rb_node`

`src_langgraph_rb_node` это альтернативный Ruby workflow runtime рядом с `src_langgraph_rb`.

Его цель:

- уйти от framework-style authoring с builder/catalog/compute-op слоями
- писать сценарии как обычный Ruby-код на `AsyncGraph`
- держать все ветвления видимыми через явные `node`, `edge`, `AsyncGraph::Command.goto`
- сохранить тот же внешний `WorkflowRunRequest` / `WorkflowRunResponse`, чтобы `src_agent` переключался только NATS subject-ом

Новый сервис не заменяет `src_langgraph_rb` внутри этого этапа. Он живет отдельно и слушает свои subject-ы:

- `nats.workflow.run.ruby.node`
- `nats.workflow.health.ruby.node`

## Что тут считается DSL

Отдельного сценарного DSL поверх runtime нет.

Канонический authoring format это сам `AsyncGraph`:

```ruby
graph = AsyncGraph::Graph.new do
  node :collect_params do |state, await|
    result = await.call(
      "collect_params",
      :llm,
      mode: "tool_params",
      input_data: {
        task: "...",
        user_message: state.dig(:req, :text)
      },
      constraints: { temperature: 0 }
    )

    if ready?(result)
      { status: "ready" }
    else
      { status: "missing" }
    end
  end

  node :router do |state|
    if state[:status] == "ready"
      AsyncGraph::Command.goto(:call_tool)
    else
      AsyncGraph::Command.goto(:ask_user)
    end
  end

  set_entry_point :collect_params
  edge :collect_params, :router
end
```

Идея простая:

- внешний I/O инициируется только через `await`
- route logic оформляется отдельной нодой
- terminal response тоже оформляется отдельной нодой
- никаких скрытых builder transforms между authoring-кодом и runtime graph нет

## Runtime shape

Слои сервиса:

| Слой | Файл | Роль |
| --- | --- | --- |
| entrypoint + NATS boundary | `lib/src_langgraph_rb_node/runtime/service.rb` | subscribe на run/health subjects, validate request, normalize reply |
| orchestration | `lib/src_langgraph_rb_node/runtime/engine.rb` | direct-start, top-level router, memory prepare/finalize, scenario run |
| AsyncGraph executor | `lib/src_langgraph_rb_node/runtime/graph_runner.rb` | loop around `Graph#step`, resolve `await`, handle forks/joins |
| external request dispatch | `lib/src_langgraph_rb_node/runtime/request_executor.rb` | переводит AsyncGraph request kinds в `call_llm` / `call_tool` |
| downstream I/O | `lib/src_langgraph_rb_node/runtime/runtime_io.rb` | NATS req-reply до `src_llm` и `src_api_gateway` |
| top-level router | `lib/src_langgraph_rb_node/runtime/router.rb` | LLM routing по metadata scenario registry |
| built-in scenarios | `lib/src_langgraph_rb_node/scenarios` | нативные `AsyncGraph::Graph` definitions |

## Request vocabulary

Встроенный executor этого runtime понимает только два `request.kind`:

- `:llm`
- `:tool`

Формат:

### `:llm`

```ruby
await.call(
  "free_speech_primary",
  :llm,
  mode: "final_response",
  input_data: {
    task: "...",
    user_message: state.dig(:req, :text),
    dialog_context: state[:dialog_context]
  },
  constraints: { temperature: 0.4 }
)
```

### `:tool`

```ruby
await.call(
  "flight_lookup",
  :tool,
  tool_name: "get_flight_status",
  args: state[:collected_params]
)
```

Других скрытых kind-ов сервис не добавляет. Если понадобится новый внешний boundary, он должен быть явно добавлен в `Runtime::RequestExecutor`.

## Как запускается сценарий

`Engine` выбирает сценарий так:

1. если в `runtime.active_workflow_id` есть id сценария, он запускается сразу
2. иначе вызывается top-level `Runtime::Router`
3. если router не дал валидный `workflow_id`, fallback идет в `free_speech@2.0.0`

Это важно:

- `active_workflow_id` работает не только как resume после `PARTIAL`
- его можно использовать как прямой старт нужного сценария извне

## Built-in scenarios

Сейчас перенесены:

- `free_speech@2.0.0`
- `where_my_flight@2.0.0`
- `find_nearest_airport@2.0.0`

### `where_my_flight`

Graph shape:

- `collect_params`
- `route_after_collect`
- `ask_missing`
- `call_status_tool`
- `route_after_tool`
- `emit_final_response`
- `emit_not_found_response`
- `emit_failed_response`
- `reroute`

### `find_nearest_airport`

Graph shape:

- `get_position`
- `route_after_position`
- `prepare_airport_search`
- `search_airports`
- `route_after_search`
- `prepare_route`
- `route_after_route_args`
- `build_route`
- `route_after_build_route`
- terminal response/error nodes

### `free_speech`

Graph shape:

- `prepare_context`
- `route_after_prepare`
- `clarify_reference`
- `compose_response`
- `emit_final_response`

## AsyncGraph execution model внутри runtime

`GraphRunner` делает следующее:

1. берет entry token
2. вызывает `graph.step(...)`
3. если узел `Suspended`, выполняет все `await` requests через `RequestExecutor`
4. повторно вызывает тот же step уже с `resolved`
5. если результат `Advanced`, отправляет токен по destinations
6. если есть fork/join topology, использует встроенные `AsyncGraph` join primitives
7. когда graph дошел до finish, забирает `state[:response]`

Для built-in сценариев этот loop чаще выглядит как последовательный graph, но runner поддерживает и fan-out/join, если следующие сценарии будут его использовать.

## Memory и runtime context

Сервис сохраняет shape memory, совместимый с текущим `src_agent`:

- `runtime.next_runtime.active_workflow_id`
- `runtime.next_runtime.pending`
- `runtime.next_runtime.context`
- `runtime.version`

В `context` остаются:

- `dialog_memory.summary`
- `dialog_memory.recent_turns`
- `artifact_memory`

## Локальный запуск

Установка:

```bash
cd src_langgraph_rb_node
bin/setup
```

Запуск:

```bash
cd src_langgraph_rb_node
NATS_URL=nats://localhost:4222 \
NATS_WORKFLOW_RUN_SUBJECT=nats.workflow.run.ruby.node \
NATS_WORKFLOW_HEALTH_SUBJECT=nats.workflow.health.ruby.node \
bundle exec ruby ./lib/src_langgraph_rb_node/runtime/service.rb
```

## Тесты

```bash
cd src_langgraph_rb_node
bundle exec rspec
```

## Где менять код

| Нужно изменить | Файл / каталог |
| --- | --- |
| сценарную логику и topology | `lib/src_langgraph_rb_node/scenarios` |
| top-level routing | `lib/src_langgraph_rb_node/runtime/router.rb` |
| AsyncGraph run loop | `lib/src_langgraph_rb_node/runtime/graph_runner.rb` |
| внешний I/O vocabulary | `lib/src_langgraph_rb_node/runtime/request_executor.rb` |
| NATS boundary и env defaults | `lib/src_langgraph_rb_node/runtime/service.rb` |

## Что intentionally не перенесено

- builder DSL
- fragment imports
- generic compute-op registry
- schema/catalog compilation layer
- `LangGraphRB` adapter

Это сознательно: новый сервис должен оставаться читаемым как обычный Ruby runtime на библиотеке, а не как framework со скрытым lowering.

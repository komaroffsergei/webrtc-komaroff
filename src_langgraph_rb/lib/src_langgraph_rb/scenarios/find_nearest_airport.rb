# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FindNearestAirport
      # Делаем `register` модульной функцией, чтобы сценарий можно было подключать без инстанса.
      module_function

      # Tool, который определяет текущую позицию пользователя.
      POSITION_TOOL = "get_current_position"

      # Tool, который ищет ближайшие аэропорты.
      SEARCH_TOOL = "search_airports_nearby"

      # Tool, который строит маршрут до выбранного аэропорта.
      BUILD_ROUTE_TOOL = "build_route"

      # Дефолтный город на случай, если позиция и LLM не дали осмысленный city.
      DEFAULT_CITY = "Moscow"

      # Дефолтный радиус поиска аэропортов.
      DEFAULT_RADIUS_KM = 50.0

      # Prompt для LLM на шаге подготовки аргументов поиска аэропортов.
      SEARCH_PARAMS_TASK = "Подготовь параметры для поиска ближайших аэропортов.\n" \
                           "Если город не указан явно, используй данные о текущей позиции из tool_results."

      # Prompt для LLM на шаге подготовки аргументов построения маршрута.
      ROUTE_PARAMS_TASK = "Подготовь параметры для построения маршрута до выбранного аэропорта.\n" \
                          "Используй текущую позицию пользователя и координаты первого найденного аэропорта."

      # Финальный prompt для пользовательского ответа после всех tool-вызовов.
      FINAL_TASK = "Сформируй финальный ответ пользователю по найденному аэропорту и маршруту.\n" \
                   "Пиши по-русски."

      # Краткий контекст сценария, который передается в final_response.
      SCENARIO_CONTEXT = "Пользователь хочет найти ближайший аэропорт и построить маршрут."

      # Схема аргументов для поиска ближайших аэропортов.
      SEARCH_TOOL_SCHEMA = {
        parameters: {
          # Город, относительно которого ищем аэропорты.
          city: { type: "string", description: "Город для поиска ближайших аэропортов" },
          # Радиус поиска в километрах.
          radius_km: { type: "number", description: "Радиус поиска в километрах", default: 50 }
        }
      }.freeze

      # Схема аргументов для построения маршрута.
      ROUTE_TOOL_SCHEMA = {
        parameters: {
          # Широта стартовой точки.
          from_lat: { type: "number" },
          # Долгота стартовой точки.
          from_lon: { type: "number" },
          # Широта конечной точки.
          to_lat: { type: "number" },
          # Долгота конечной точки.
          to_lon: { type: "number" }
        }
      }.freeze

      # Регистрирует сценарий поиска ближайшего аэропорта.
      def register(builder)
        # Уникальный id сценария.
        builder.scenario("find_nearest_airport@2.0.0") do
          # Человекочитаемое название.
          title "Find Nearest Airport"

          # Короткое описание для разработчика.
          description "Resolve position, search airports, build a route, and respond"

          # Описание для router'а.
          routing_description "Найти ближайший аэропорт и построить маршрут до него"

          # Служебные теги.
          tags :airport, :geo

          # Сценарий использует LLM для подготовки args, вызывает tools и отдает client_events.
          capabilities :tool_params, :tool_call, :client_events

          # Нужен контекст и поддержка artifact_memory,
          # потому что маршрут и аэропорты потом сохраняются в client_events -> memory.
          runtime_flags context_required: true, artifact_memory: true

          # Профиль поиска аэропортов:
          # в нем живет tool name, prompt, schema и дефолты этого шага.
          tool_profile :airport_search,
            tool_name: SEARCH_TOOL, # Реальный tool для поиска аэропортов.
            params_task: SEARCH_PARAMS_TASK, # Prompt для LLM сборки search args.
            tool_schema: SEARCH_TOOL_SCHEMA, # Схема допустимых аргументов поиска.
            default_city: DEFAULT_CITY, # Дефолтный город.
            default_radius_km: DEFAULT_RADIUS_KM, # Дефолтный радиус поиска.
            failure_message: "Не удалось найти ближайшие аэропорты." # Текст при ошибке tool'а.

          # Профиль маршрута:
          # здесь хранится и prompt для route args, и финальный prompt для ответа пользователю.
          tool_profile :airport_route,
            tool_name: BUILD_ROUTE_TOOL, # Реальный tool для построения маршрута.
            params_task: ROUTE_PARAMS_TASK, # Prompt для подготовки route args.
            final_task: FINAL_TASK, # Prompt для итогового ответа пользователю.
            tool_schema: ROUTE_TOOL_SCHEMA, # Схема route-аргументов.
            scenario_context: SCENARIO_CONTEXT, # Контекст сценария для final_response.
            failure_message: "Не удалось построить маршрут.", # Текст ошибки route tool.
            fallback_message: "Маршрут построен." # Fallback, если LLM не вернула текст.

          # Ниже описывается граф выполнения сценария.
          graph do
            # Подключаем оба стандартных хвоста.
            use_default_tails

            # Стартовый узел:
            # сначала всегда определяем текущую позицию пользователя.
            entry_point :get_position

            # Прямой tool-call шаг:
            # под капотом это `kind: tool_call`, но authoring DSL не требует писать это явно.
            tool :get_position, tool_name: POSITION_TOOL, args_source: :empty_args,
              failure_message: "Не удалось получить текущую позицию." # Ошибка, если position tool недоступен.

            # Узел для FAILED-ответа после ошибки определения позиции.
            failed :position_failed

            # Compute-helper:
            # берет ответ get_position, спрашивает LLM о search args
            # и складывает current_position/tool_results/search_args в state.
            airport_search_params :prepare_airport_search,
              profile: :airport_search, # Какой tool_profile использовать для поиска.
              position_tool_name: POSITION_TOOL, # Какой tool дал позицию.
              position_source: response_of(:get_position) # Из какого state key брать ответ get_position.

            # Вызов tool'а поиска аэропортов с аргументами, собранными на предыдущем шаге.
            tool :search_airports, tool_name: SEARCH_TOOL, args_source: :search_args,
              failure_message: "Не удалось найти ближайшие аэропорты." # Ошибка search tool.

            # Узел FAILED-ответа, если поиск аэропортов сломался.
            failed :search_failed

            # Compute-helper:
            # берет найденные аэропорты + текущую позицию
            # и собирает route args через LLM + fallback-нормализацию.
            airport_route_params :prepare_route,
              profile: :airport_route, # Профиль route-шага.
              search_tool_name: SEARCH_TOOL, # Какой tool выдал список аэропортов.
              search_response_key: response_of(:search_airports), # Где в state лежит ответ поиска аэропортов.
              failure_message: "Не удалось собрать координаты для маршрута." # Ошибка при нехватке route args.

            # Узел FAILED-ответа, если route args собрать не удалось.
            failed :route_args_failed

            # Финальный compute-helper:
            # вызывает build_route, затем LLM финализирует текст ответа
            # и формируются client_events для фронтенда.
            route_response :build_route,
              profile: :airport_route, # Профиль маршрута и финального ответа.
              args_source: :route_args, # Откуда брать аргументы для build_route.
              search_response_key: response_of(:search_airports) # Откуда брать airports для client_events.

            # Узел FAILED-ответа, если build_route tool завершился ошибкой.
            failed :build_route_failed

            # После get_position читаем built-in router `tool_status`
            # и либо продолжаем сценарий, либо уходим в failed.
            route_tool_status :get_position, ok: :prepare_airport_search, failed: :position_failed

            # Если позиция получена, сразу переходим к реальному поиску аэропортов.
            edge :prepare_airport_search, :search_airports

            # После search_airports снова маршрутизируемся по built-in `tool_status`.
            route_tool_status :search_airports, ok: :prepare_route, failed: :search_failed

            # После prepare_route читаем auto-generated status key
            # и либо строим маршрут, либо завершаемся ошибкой.
            route_status :prepare_route, {
              "ready" => :build_route,
              "failed" => :route_args_failed
            }

            # После build_route читаем auto-generated status key:
            # успех идет в final tail, ошибка — в failed узел.
            route_status :build_route, {
              "done" => final,
              "failed" => :build_route_failed
            }

            # Все FAILED-узлы уже сформировали response,
            # поэтому их остается только довести до terminal tail.
            finish_with_state :position_failed, :search_failed, :route_args_failed, :build_route_failed
          end
        end
      end
    end
  end
end

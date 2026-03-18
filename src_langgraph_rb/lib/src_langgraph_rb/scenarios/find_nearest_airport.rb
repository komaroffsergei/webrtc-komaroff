# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FindNearestAirport
      module_function

      POSITION_TOOL = "get_current_position"
      SEARCH_TOOL = "search_airports_nearby"
      BUILD_ROUTE_TOOL = "build_route"
      DEFAULT_CITY = "Moscow"
      DEFAULT_RADIUS_KM = 50.0
      SEARCH_PARAMS_TASK = "Подготовь параметры для поиска ближайших аэропортов.\n" \
                           "Если город не указан явно, используй данные о текущей позиции из tool_results."
      ROUTE_PARAMS_TASK = "Подготовь параметры для построения маршрута до выбранного аэропорта.\n" \
                          "Используй текущую позицию пользователя и координаты первого найденного аэропорта."
      FINAL_TASK = "Сформируй финальный ответ пользователю по найденному аэропорту и маршруту.\n" \
                   "Пиши по-русски."
      SCENARIO_CONTEXT = "Пользователь хочет найти ближайший аэропорт и построить маршрут."
      SEARCH_TOOL_SCHEMA = {
        parameters: {
          city: { type: "string", description: "Город для поиска ближайших аэропортов" },
          radius_km: { type: "number", description: "Радиус поиска в километрах", default: 50 }
        }
      }.freeze
      ROUTE_TOOL_SCHEMA = {
        parameters: {
          from_lat: { type: "number" },
          from_lon: { type: "number" },
          to_lat: { type: "number" },
          to_lon: { type: "number" }
        }
      }.freeze

      def register(builder)
        builder.scenario("find_nearest_airport@2.0.0") do
          title "Find Nearest Airport"
          description "Resolve position, search airports, build a route, and respond"
          routing_description "Найти ближайший аэропорт и построить маршрут до него"
          tags :airport, :geo
          capabilities :tool_params, :tool_call, :client_events
          required_tools :get_current_position, :search_airports_nearby, :build_route
          runtime_flags context_required: true, artifact_memory: true

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :get_position

            node :get_position, kind: :tool_call, tool_name: POSITION_TOOL, args_source: :empty_args, result_key: :position_response,
              failure_message: "Не удалось получить текущую позицию."
            node :position_failed, kind: :failed_response, message_source: :error_message
            node :prepare_airport_search, kind: :compute, op: :prepare_airport_search, task: SEARCH_PARAMS_TASK,
              position_tool_name: POSITION_TOOL, search_tool_name: SEARCH_TOOL, tool_schema: SEARCH_TOOL_SCHEMA,
              default_city: DEFAULT_CITY, default_radius_km: DEFAULT_RADIUS_KM,
              position_source: :position_response, position_key: :current_position, tool_results_key: :tool_results,
              args_key: :search_args
            node :search_airports, kind: :tool_call, tool_name: SEARCH_TOOL, args_source: :search_args, result_key: :search_response,
              failure_message: "Не удалось найти ближайшие аэропорты."
            node :search_failed, kind: :failed_response, message_source: :error_message
            node :prepare_route, kind: :compute, op: :prepare_airport_route, task: ROUTE_PARAMS_TASK,
              search_tool_name: SEARCH_TOOL, route_tool_name: BUILD_ROUTE_TOOL, tool_schema: ROUTE_TOOL_SCHEMA,
              search_response_key: :search_response, tool_results_key: :tool_results,
              current_position_key: :current_position, route_args_key: :route_args,
              status_key: :route_args_status, failure_message: "Не удалось собрать координаты для маршрута."
            node :route_args_failed, kind: :failed_response, message_source: :error_message
            node :build_route, kind: :compute, op: :build_route_with_response, tool_name: BUILD_ROUTE_TOOL,
              args_source: :route_args, search_response_key: :search_response, tool_results_key: :tool_results,
              current_position_key: :current_position, task: FINAL_TASK, scenario_context: SCENARIO_CONTEXT,
              status_key: :airport_route_result_status, failure_message: "Не удалось построить маршрут.",
              fallback_message: "Маршрут построен."
            node :build_route_failed, kind: :failed_response, message_source: :error_message

            conditional_edge :get_position, :tool_status, {
              "ok" => :prepare_airport_search,
              "failed" => :position_failed
            }
            edge :position_failed, ref(:terminal, :respond)

            edge :prepare_airport_search, :search_airports
            conditional_edge :search_airports, :tool_status, {
              "ok" => :prepare_route,
              "failed" => :search_failed
            }
            edge :search_failed, ref(:terminal, :respond)

            conditional_edge :prepare_route, :route_args_status, {
              "ready" => :build_route,
              "failed" => :route_args_failed
            }
            edge :route_args_failed, ref(:terminal, :respond)

            conditional_edge :build_route, :airport_route_result_status, {
              "done" => ref(:final, :respond),
              "failed" => :build_route_failed
            }
            edge :build_route_failed, ref(:terminal, :respond)
          end
        end
      end
    end
  end
end

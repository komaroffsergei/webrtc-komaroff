# frozen_string_literal: true

module SrcLanggraphRbNode
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

      def definition
        ScenarioDefinition.new(
          id: Runtime::ScenarioIds::FIND_NEAREST_AIRPORT,
          metadata: ScenarioMetadata.new(
            title: "Find Nearest Airport",
            description: "Resolve position, search airports, build a route, and respond",
            routing_description: "Найти ближайший аэропорт и построить маршрут до него",
            tags: %i[airport geo]
          ),
          graph: build_graph
        )
      end

      def build_graph
        AsyncGraph::Graph.new do
          node :get_position do |state, await|
            tool_resp = await.call(
              "get_position",
              :tool,
              tool_name: POSITION_TOOL,
              args: {}
            )

            if tool_resp[:ok]
              {
                position_response: tool_resp,
                position_status: "ok"
              }
            else
              code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
              code = "tool_failed" if code.empty?
              message = "Не удалось получить текущую позицию."
              {
                error_code: code,
                error_message: message,
                error_client_handler: {
                  command: "SHOW_ERROR_MESSAGE",
                  payload: { message: message, code: code }
                },
                position_status: "failed"
              }
            end
          end

          node :route_after_position do |state|
            if state[:position_status] == "ok"
              AsyncGraph::Command.goto(:prepare_airport_search)
            else
              AsyncGraph::Command.goto(:position_failed)
            end
          end

          node :prepare_airport_search do |state, await|
            req = state.fetch(:req)
            position_resp = Runtime::Util.extract_hash(state[:position_response])
            position_data = Scenarios::FindNearestAirport.extract_nested_data(position_resp[:data] || position_resp) || {}
            tool_results = [{ tool_name: POSITION_TOOL, result: position_resp[:data] || position_resp }]

            params_resp = await.call(
              "airport_search_params",
              :llm,
              mode: "tool_params",
              input_data: {
                task: SEARCH_PARAMS_TASK,
                user_message: req[:text],
                tool_name: SEARCH_TOOL,
                tool_schema: SEARCH_TOOL_SCHEMA,
                tool_results: tool_results,
                dialog_context: state[:dialog_context].to_s
              },
              constraints: { temperature: 0 }
            )
            extracted = Scenarios::FindNearestAirport.normalize_tool_params(params_resp)
            city = extracted[:city].to_s.strip
            city = position_data[:city].to_s.strip if city.empty?
            city = DEFAULT_CITY if city.empty?
            radius_km = Runtime::Util.float(extracted[:radius_km], default: DEFAULT_RADIUS_KM) || DEFAULT_RADIUS_KM

            {
              current_position: position_data,
              tool_results: tool_results,
              search_args: { city: city, radius_km: radius_km }
            }
          end

          node :search_airports do |state, await|
            tool_resp = await.call(
              "search_airports",
              :tool,
              tool_name: SEARCH_TOOL,
              args: Runtime::Util.extract_hash(state[:search_args])
            )

            if tool_resp[:ok]
              {
                search_response: tool_resp,
                search_status: "ok"
              }
            else
              code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
              code = "tool_failed" if code.empty?
              message = "Не удалось найти ближайшие аэропорты."
              {
                error_code: code,
                error_message: message,
                error_client_handler: {
                  command: "SHOW_ERROR_MESSAGE",
                  payload: { message: message, code: code }
                },
                search_status: "failed"
              }
            end
          end

          node :route_after_search do |state|
            if state[:search_status] == "ok"
              AsyncGraph::Command.goto(:prepare_route)
            else
              AsyncGraph::Command.goto(:search_failed)
            end
          end

          node :prepare_route do |state, await|
            req = state.fetch(:req)
            search_resp = Runtime::Util.extract_hash(state[:search_response])
            tool_results = Array(state[:tool_results]) + [{ tool_name: SEARCH_TOOL, result: search_resp[:data] || search_resp }]

            params_resp = await.call(
              "airport_route_params",
              :llm,
              mode: "tool_params",
              input_data: {
                task: ROUTE_PARAMS_TASK,
                user_message: req[:text],
                tool_name: BUILD_ROUTE_TOOL,
                tool_schema: ROUTE_TOOL_SCHEMA,
                tool_results: tool_results,
                dialog_context: state[:dialog_context].to_s
              },
              constraints: { temperature: 0 }
            )
            route_args = Scenarios::FindNearestAirport.normalize_route_args(
              Scenarios::FindNearestAirport.normalize_tool_params(params_resp),
              Runtime::Util.extract_hash(state[:current_position]),
              Scenarios::FindNearestAirport.extract_nested_data(search_resp[:data] || search_resp) || {}
            )

            if route_args
              {
                route_args: route_args,
                tool_results: tool_results,
                route_args_status: "ready"
              }
            else
              {
                error_code: "route_params_missing",
                error_message: "Не удалось собрать координаты для маршрута.",
                route_args_status: "failed"
              }
            end
          end

          node :route_after_route_args do |state|
            if state[:route_args_status] == "ready"
              AsyncGraph::Command.goto(:build_route)
            else
              AsyncGraph::Command.goto(:route_args_failed)
            end
          end

          node :build_route do |state, await|
            req = state.fetch(:req)
            route_resp = await.call(
              "build_route",
              :tool,
              tool_name: BUILD_ROUTE_TOOL,
              args: Runtime::Util.extract_hash(state[:route_args])
            )

            unless route_resp[:ok]
              code = Runtime::Util.extract_hash(route_resp[:error])[:code].to_s
              code = "tool_failed" if code.empty?
              message = "Не удалось построить маршрут."
              next {
                error_code: code,
                error_message: message,
                error_client_handler: {
                  command: "SHOW_ERROR_MESSAGE",
                  payload: { message: message, code: code }
                },
                build_route_status: "failed"
              }
            end

            tool_results = Array(state[:tool_results]) + [{ tool_name: BUILD_ROUTE_TOOL, result: route_resp[:data] }]
            final_resp = await.call(
              "airport_final_response",
              :llm,
              mode: "final_response",
              input_data: {
                task: FINAL_TASK,
                user_message: req[:text],
                tool_results: tool_results,
                scenario_context: SCENARIO_CONTEXT,
                dialog_context: state[:dialog_context].to_s
              },
              constraints: { temperature: 0.1 }
            )
            message = Scenarios::FindNearestAirport.extract_llm_text(final_resp)
            message = "Маршрут построен." if message.empty?

            airports_data = Scenarios::FindNearestAirport.extract_nested_data(state.dig(:search_response, :data) || state[:search_response]) || {}
            route_data = Scenarios::FindNearestAirport.extract_nested_data(route_resp[:data]) || {}
            {
              response_message: message,
              client_events: [
                { command: "SET_POSITION", payload: { data: { current_position: Runtime::Util.extract_hash(state[:current_position]) } } },
                { command: "SET_AIRPORTS", payload: { data: { airports: airports_data[:airports] || [] } } },
                { command: "BUILD_ROUTE", payload: { data: { route: route_data } } }
              ],
              build_route_status: "done"
            }
          end

          node :route_after_build_route do |state|
            if state[:build_route_status] == "done"
              AsyncGraph::Command.goto(:emit_final_response)
            else
              AsyncGraph::Command.goto(:build_route_failed)
            end
          end

          node :emit_final_response do |state|
            {
              response: Runtime::Responses.done_response(
                state.fetch(:req),
                state[:response_message],
                client_events: Array(state[:client_events])
              )
            }
          end

          node :position_failed do |state|
            { response: Scenarios::FindNearestAirport.failed_response(state) }
          end

          node :search_failed do |state|
            { response: Scenarios::FindNearestAirport.failed_response(state) }
          end

          node :route_args_failed do |state|
            { response: Scenarios::FindNearestAirport.failed_response(state) }
          end

          node :build_route_failed do |state|
            { response: Scenarios::FindNearestAirport.failed_response(state) }
          end

          set_entry_point :get_position
          edge :get_position, :route_after_position
          edge :prepare_airport_search, :search_airports
          edge :search_airports, :route_after_search
          edge :prepare_route, :route_after_route_args
          edge :build_route, :route_after_build_route
          set_finish_point :emit_final_response
          set_finish_point :position_failed
          set_finish_point :search_failed
          set_finish_point :route_args_failed
          set_finish_point :build_route_failed
        end
      end

      def failed_response(state)
        code = state[:error_code].to_s
        code = "workflow_failed" if code.empty?
        message = state[:error_message].to_s
        message = "Workflow failed." if message.empty?

        Runtime::Responses.failed_response(
          state.fetch(:req),
          code: code,
          message: message,
          client_handler: state[:error_client_handler]
        )
      end

      def normalize_tool_params(resp)
        data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
        extracted = data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
        extracted
      end

      def extract_llm_text(resp)
        data = Runtime::Util.extract_hash(resp[:data])
        value = data[:response_text]
        value.is_a?(String) ? value.strip : ""
      end

      def extract_nested_data(payload)
        data = Runtime::Util.extract_hash(payload)
        inner = data[:data]
        inner.is_a?(Hash) ? Runtime::Util.extract_hash(inner) : nil
      end

      def normalize_route_args(extracted, current_position, airports_data)
        out = {}
        %i[from_lat from_lon to_lat to_lon].each do |key|
          value = Runtime::Util.float(Runtime::Util.extract_hash(extracted)[key])
          out[key] = value if value
        end
        out[:from_lat] ||= Runtime::Util.float(current_position[:lat])
        out[:from_lon] ||= Runtime::Util.float(current_position[:lon])

        first_airport = Array(airports_data[:airports]).first
        airport = first_airport.is_a?(Hash) ? Runtime::Util.extract_hash(first_airport) : {}
        out[:to_lat] ||= Runtime::Util.float(airport[:lat])
        out[:to_lon] ||= Runtime::Util.float(airport[:lon])

        required = %i[from_lat from_lon to_lat to_lon]
        return nil unless required.all? { |key| out.key?(key) }

        required.each_with_object({}) { |key, memo| memo[key] = out[key] }
      end
    end
  end
end

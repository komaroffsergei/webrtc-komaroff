# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Scenarios
      module FindNearestAirport
        module_function

        CFG = Runtime::ConfigLoader.load_config("find_nearest_airport")
        PROMPTS = Runtime::ConfigLoader.dict_value(CFG[:prompts])
        TOOLS = Runtime::ConfigLoader.dict_value(CFG[:tools])
        DEFAULTS = Runtime::ConfigLoader.dict_value(CFG[:defaults])
        SCHEMAS = Runtime::ConfigLoader.dict_value(CFG[:schemas])

        TOOL_GET_POSITION = (TOOLS[:position] || "get_current_position").to_s
        TOOL_SEARCH_AIRPORTS = (TOOLS[:search_airports] || "search_airports_nearby").to_s
        TOOL_BUILD_ROUTE = (TOOLS[:build_route] || "build_route").to_s
        DEFAULT_CITY = (DEFAULTS[:search_city] || "Moscow").to_s
        DEFAULT_RADIUS_KM = Runtime::Util.float(DEFAULTS[:search_radius_km], default: 50.0) || 50.0
        SEARCH_PARAMS_TASK = Runtime::ConfigLoader.text_block(
          PROMPTS[:search_params_task],
          "Подготовь параметры для поиска ближайших аэропортов.\nЕсли город не указан явно, используй данные о текущей позиции из tool_results."
        )
        ROUTE_PARAMS_TASK = Runtime::ConfigLoader.text_block(
          PROMPTS[:route_params_task],
          "Подготовь параметры для построения маршрута до выбранного аэропорта.\nИспользуй текущую позицию пользователя и координаты первого найденного аэропорта."
        )
        FINAL_TASK = Runtime::ConfigLoader.text_block(
          PROMPTS[:final_task],
          "Сформируй финальный ответ пользователю по найденному аэропорту и маршруту. Пиши по-русски."
        )
        SCENARIO_CONTEXT = Runtime::ConfigLoader.text_block(
          PROMPTS[:scenario_context],
          "Пользователь хочет найти ближайший аэропорт и построить маршрут."
        )
        SEARCH_TOOL_SCHEMA = Runtime::ConfigLoader.dict_value(
          SCHEMAS[:search_tool_schema],
          {
            parameters: {
              city: { type: "string", description: "Город для поиска ближайших аэропортов" },
              radius_km: { type: "number", description: "Радиус поиска в километрах", default: 50 }
            }
          }
        )
        ROUTE_TOOL_SCHEMA = Runtime::ConfigLoader.dict_value(
          SCHEMAS[:route_tool_schema],
          {
            parameters: {
              from_lat: { type: "number" },
              from_lon: { type: "number" },
              to_lat: { type: "number" },
              to_lon: { type: "number" }
            }
          }
        )

        def prepare_search(state, io:)
          req = state.fetch(:req)
          pos_resp = Runtime::Util.extract_hash(state[:position_response])
          pos_data = Common.extract_nested_data(pos_resp[:data] || pos_resp) || {}
          tool_results = [{ tool_name: TOOL_GET_POSITION, result: pos_resp[:data] || pos_resp }]
          search_params_resp = io.call_llm(
            parent: req,
            mode: "tool_params",
            input_data: {
              task: SEARCH_PARAMS_TASK,
              user_message: req[:text],
              tool_name: TOOL_SEARCH_AIRPORTS,
              tool_schema: SEARCH_TOOL_SCHEMA,
              tool_results: tool_results,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )
          search_params = Common.normalize_tool_params(search_params_resp)[:extracted]
          city = search_params[:city].to_s.strip
          radius_km = Runtime::Util.float(search_params[:radius_km])
          city = pos_data[:city].to_s.strip if city.empty?
          city = DEFAULT_CITY if city.empty?

          {
            current_position: pos_data,
            tool_results: tool_results,
            search_args: { city: city, radius_km: radius_km || DEFAULT_RADIUS_KM }
          }
        end

        def prepare_route(state, io:)
          req = state.fetch(:req)
          search_resp = Runtime::Util.extract_hash(state[:search_response])
          tool_results = Array(state[:tool_results]) + [{ tool_name: TOOL_SEARCH_AIRPORTS, result: search_resp[:data] || search_resp }]
          route_params_resp = io.call_llm(
            parent: req,
            mode: "tool_params",
            input_data: {
              task: ROUTE_PARAMS_TASK,
              user_message: req[:text],
              tool_name: TOOL_BUILD_ROUTE,
              tool_schema: ROUTE_TOOL_SCHEMA,
              tool_results: tool_results,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )
          route_params = Common.normalize_tool_params(route_params_resp)[:extracted]
          airports_data = Common.extract_nested_data(search_resp[:data] || search_resp) || {}
          route_args = normalize_route_args(route_params, Runtime::Util.extract_hash(state[:current_position]), airports_data)
          return { route_args: route_args, tool_results: tool_results, route_args_status: "ready" } if route_args

          {
            error_code: "route_params_missing",
            error_message: "Не удалось собрать координаты для маршрута.",
            route_args_status: "failed"
          }
        end

        def build_route(state, io:)
          req = state.fetch(:req)
          route_resp = io.call_tool(parent: req, tool_name: TOOL_BUILD_ROUTE, args: Runtime::Util.extract_hash(state[:route_args]))
          unless route_resp[:ok]
            code = Runtime::Util.extract_hash(route_resp[:error])[:code].to_s
            code = "tool_failed" if code.empty?
            return {
              error_code: code,
              error_message: "Не удалось построить маршрут.",
              airport_route_result_status: "failed"
            }
          end

          search_resp = Runtime::Util.extract_hash(state[:search_response])
          tool_results = Array(state[:tool_results]) + [{ tool_name: TOOL_BUILD_ROUTE, result: route_resp[:data] }]
          final_resp = io.call_llm(
            parent: req,
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
          message = Common.extract_llm_text(final_resp) || "Маршрут построен."
          airports_data = Common.extract_nested_data(search_resp[:data] || search_resp) || {}
          route_data = Common.extract_nested_data(route_resp[:data]) || {}
          {
            response_message: message,
            client_events: [
              { command: "SET_POSITION", payload: { data: { current_position: Runtime::Util.extract_hash(state[:current_position]) } } },
              { command: "SET_AIRPORTS", payload: { data: { airports: airports_data[:airports] || [] } } },
              { command: "BUILD_ROUTE", payload: { data: { route: route_data } } }
            ],
            airport_route_result_status: "done"
          }
        end

        def normalize_route_args(extracted, pos_data, airports_data)
          out = {}
          %i[from_lat from_lon to_lat to_lon].each do |key|
            val = Runtime::Util.float(Runtime::Util.extract_hash(extracted)[key])
            out[key] = val if val
          end
          out[:from_lat] ||= Runtime::Util.float(pos_data[:lat])
          out[:from_lon] ||= Runtime::Util.float(pos_data[:lon])

          airports = Array(airports_data[:airports])
          first = airports.first.is_a?(Hash) ? Runtime::Util.extract_hash(airports.first) : {}
          out[:to_lat] ||= Runtime::Util.float(first[:lat])
          out[:to_lon] ||= Runtime::Util.float(first[:lon])
          required = %i[from_lat from_lon to_lat to_lon]
          required.all? { |key| out.key?(key) } ? required.each_with_object({}) { |key, acc| acc[key] = out[key] } : nil
        end
        private_class_method :normalize_route_args
      end
    end
  end
end

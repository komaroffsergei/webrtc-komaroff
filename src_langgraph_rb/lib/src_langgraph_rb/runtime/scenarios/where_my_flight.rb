# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Scenarios
      module WhereMyFlight
        module_function

        CFG = Runtime::ConfigLoader.load_config("where_my_flight")
        PROMPTS = Runtime::ConfigLoader.dict_value(CFG[:prompts])
        TOOLS = Runtime::ConfigLoader.dict_value(CFG[:tools])
        SCHEMAS = Runtime::ConfigLoader.dict_value(CFG[:schemas])

        TOOL_NAME = (TOOLS[:status] || "get_flight_status").to_s
        TOOL_PARAMS_TASK = Runtime::ConfigLoader.text_block(
          PROMPTS[:tool_params_task],
          "Определи параметры для поиска статуса рейса.\n" \
          "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n" \
          "Если параметр распознан как номер рейса — нормализуй его (удали пробелы внутри номера рейса)."
        )
        FINAL_TASK = Runtime::ConfigLoader.text_block(
          PROMPTS[:final_task],
          "Сформируй понятный ответ пользователю по результату поиска рейса. Пиши по-русски."
        )
        SCENARIO_CONTEXT = Runtime::ConfigLoader.text_block(
          PROMPTS[:scenario_context],
          "Пользователь хочет узнать статус рейса. Ответ должен быть кратким и на русском языке."
        )
        ASK_INPUT_DEFAULT = Runtime::ConfigLoader.text_block(
          PROMPTS[:ask_input_default],
          "Укажите номер рейса (например, SU123) или фамилию пассажира."
        )
        TOOL_SCHEMA = Runtime::ConfigLoader.dict_value(
          SCHEMAS[:status_tool_schema],
          {
            parameters: {
              flight_number: { type: "string", description: "Номер рейса, например SU123" },
              last_name: { type: "string", description: "Фамилия пассажира" }
            }
          }
        )
        FLIGHT_FOLLOWUP_RE = /\b(рейс|flight|номер|фамил|пассажир|su\d|[A-Za-zА-Яа-яЁё]{2,3}\s?\d{1,4})\b/i

        def collect_params(state, io:, engine:)
          req = state.fetch(:req)
          pending = Runtime::Util.extract_hash(req.dig(:runtime, :pending))
          had_pending = !pending.empty?
          prev = pending[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(pending[:extracted]) : {}

          params_resp = io.call_llm(
            parent: req,
            mode: "tool_params",
            input_data: {
              task: TOOL_PARAMS_TASK,
              user_message: req[:text],
              tool_name: TOOL_NAME,
              tool_schema: TOOL_SCHEMA,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0 }
          )
          parsed = Common.normalize_tool_params(params_resp)
          merged = Common.merge_non_empty_params(prev, parsed[:extracted])

          has_flight = merged[:flight_number].is_a?(String) && !merged[:flight_number].strip.empty?
          has_last = merged[:last_name].is_a?(String) && !merged[:last_name].strip.empty?
          return { merged_params: merged, flight_param_status: "ready" } if has_flight || has_last

          if had_pending
            if FLIGHT_FOLLOWUP_RE.match?(req[:text].to_s)
              prompt = parsed[:prompt].to_s.strip
              prompt = ASK_INPUT_DEFAULT if prompt.empty?
              return {
                merged_params: merged,
                response_prompt: prompt,
                pending_state: pending_state(merged, prompt),
                flight_param_status: "missing"
              }
            end

            _summary, _recent, context_extra = Runtime::Memory.memory_from_context(req.dig(:runtime, :context))
            context_artifacts = Runtime::Util.extract_hash(context_extra[:artifact_memory])
            scenario_id, _routing = engine.choose_scenario(
              req,
              dialog_context: state[:dialog_context].to_s,
              excluded_scenarios: [Runtime::ScenarioIds::WHERE_MY_FLIGHT],
              context_artifacts: context_artifacts
            )
            return { reroute_scenario_id: scenario_id, flight_param_status: "reroute" }
          end

          prompt = parsed[:prompt].to_s.strip
          prompt = ASK_INPUT_DEFAULT if prompt.empty?
          {
            merged_params: merged,
            response_prompt: prompt,
            pending_state: pending_state(merged, prompt),
            flight_param_status: "missing"
          }
        end

        def pending_state(merged, prompt)
          {
            type: "tool_params",
            scenario_id: Runtime::ScenarioIds::WHERE_MY_FLIGHT,
            tool_name: TOOL_NAME,
            extracted: merged,
            missing: ["flight_number_or_last_name"],
            prompt: prompt
          }
        end
        private_class_method :pending_state

        def lookup_tool(state, io:)
          req = state.fetch(:req)
          merged = Runtime::Util.extract_hash(state[:merged_params])
          args = {}
          args[:flight_number] = merged[:flight_number].to_s.strip if merged[:flight_number].is_a?(String) && !merged[:flight_number].strip.empty?
          args[:last_name] = merged[:last_name].to_s.strip if merged[:last_name].is_a?(String) && !merged[:last_name].strip.empty?

          tool_resp = io.call_tool(parent: req, tool_name: TOOL_NAME, args: args)
          unless tool_resp[:ok]
            code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
            code = "tool_failed" if code.empty?
            if code == "not_found"
              return { response_message: "Статус рейса не найден.", flight_tool_result_status: "not_found" }
            end

            return {
              error_code: code,
              error_message: "Не удалось получить статус рейса.",
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: "Не удалось получить статус рейса.", code: code }
              },
              flight_tool_result_status: "failed"
            }
          end

          final_resp = io.call_llm(
            parent: req,
            mode: "final_response",
            input_data: {
              task: FINAL_TASK,
              user_message: req[:text],
              tool_results: [{ tool_name: TOOL_NAME, result: tool_resp[:data] }],
              scenario_context: SCENARIO_CONTEXT,
              dialog_context: state[:dialog_context].to_s
            },
            constraints: { temperature: 0.1 }
          )
          message = Common.extract_llm_text(final_resp) || format_flight_message(tool_resp[:data])
          { response_message: message, flight_tool_result_status: "done" }
        end

        def reroute(state, engine:)
          scenario_id = state[:reroute_scenario_id].to_s
          response = engine.run_selected_scenario(scenario_id, state)
          { response: response }
        end

        def format_flight_message(tool_data)
          data = Common.extract_nested_data(tool_data) || {}
          flight = data[:flight].is_a?(Hash) ? Runtime::Util.extract_hash(data[:flight]) : {}
          return "Статус рейса не найден." if flight.empty?

          fn = flight[:flight_number].to_s.strip
          fn = "рейс" if fn.empty?
          src = flight[:from].to_s.strip
          src = "?" if src.empty?
          dst = flight[:to].to_s.strip
          dst = "?" if dst.empty?
          dep = flight[:departure_time].to_s.strip
          arr = flight[:arrival_time].to_s.strip
          status = flight[:status].to_s.strip.upcase
          dep_short = dep.length >= 16 && dep.include?("T") ? dep[11, 5] : dep
          arr_short = arr.length >= 16 && arr.include?("T") ? arr[11, 5] : arr
          status_map = {
            "ON_TIME" => "вовремя",
            "DELAYED" => "задерживается",
            "CANCELLED" => "отменен"
          }
          "Рейс #{fn} (#{src} → #{dst}), вылет #{dep_short}, прибытие #{arr_short}. Статус: #{status_map[status] || status.downcase || 'неизвестен'}."
        end
        private_class_method :format_flight_message
      end
    end
  end
end

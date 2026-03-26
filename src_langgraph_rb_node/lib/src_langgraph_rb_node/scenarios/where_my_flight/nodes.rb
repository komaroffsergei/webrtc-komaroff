# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      class Nodes < BaseNodes
        TOOL_NAME = "get_flight_status"
        TOOL_PARAMS_TASK = "Определи параметры для поиска статуса рейса.\n" \
                           "Если параметров не хватает, верни missing и задай пользователю уточняющий вопрос на русском.\n" \
                           "Если параметр распознан как номер рейса, нормализуй его (удали пробелы внутри номера)."
        FINAL_TASK = "Сформируй понятный ответ пользователю по результату поиска рейса.\n" \
                     "Пиши по-русски."
        SCENARIO_CONTEXT = "Пользователь хочет узнать статус рейса.\n" \
                           "Ответ должен быть кратким и на русском языке."
        ASK_INPUT_DEFAULT = "Укажите номер рейса (например, SU123) или фамилию пассажира."
        TOOL_SCHEMA = {
          parameters: {
            flight_number: { type: "string", description: "Номер рейса, например SU123" },
            last_name: { type: "string", description: "Фамилия пассажира" }
          }
        }.freeze
        FOLLOWUP_RE = /\b(рейс|flight|номер|фамил|пассажир|su\d|[A-Za-zА-Яа-яЁё]{2,3}\s?\d{1,4})\b/i

        def collect_params(state, await)
          req = state.fetch(:req)
          pending = Runtime::Util.extract_hash(req.dig(:runtime, :pending))
          had_pending = !pending.empty?
          previous = Runtime::Util.extract_hash(pending[:extracted])

          params_resp = await.call(
            "collect_params",
            :llm,
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

          parsed = normalize_tool_params(params_resp)
          merged = merge_non_empty_params(previous, parsed[:extracted])
          if ready_with_any_field?(merged, %i[flight_number last_name])
            { collected_params: merged, collect_status: "ready" }
          else
            prompt = parsed[:prompt].to_s.strip
            prompt = ASK_INPUT_DEFAULT if prompt.empty?
            pending_state = {
              type: "tool_params",
              scenario_id: state[:current_scenario_id],
              tool_name: TOOL_NAME,
              extracted: merged,
              missing: ["flight_number_or_last_name"],
              prompt: prompt
            }

            if had_pending && !FOLLOWUP_RE.match?(req[:text].to_s)
              available_scenarios = filtered_router_scenarios(state, state[:current_scenario_id])
              reroute_resp = await.call(
                "reroute_decision",
                :llm,
                mode: "routing_decision",
                input_data: {
                  task: Runtime::Router::ROUTER_TASK,
                  text: req[:text],
                  available_scenarios: available_scenarios,
                  dialog_context: state[:dialog_context].to_s,
                  context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts])
                },
                constraints: { temperature: 0 }
              )
              reroute_id = normalize_routing_choice(reroute_resp, available_scenarios)
              { reroute_scenario_id: reroute_id, collect_status: "reroute" }
            else
              {
                collected_params: merged,
                collect_prompt: prompt,
                collect_pending: pending_state,
                collect_status: "missing"
              }
            end
          end
        end

        def route_after_collect(state)
          case state[:collect_status]
          when "ready"
            AsyncGraph::Command.goto(:call_status_tool)
          when "missing"
            AsyncGraph::Command.goto(:ask_missing)
          when "reroute"
            AsyncGraph::Command.goto(:reroute)
          else
            AsyncGraph::Command.update_and_goto(
              {
                error_code: "collect_params_failed",
                error_message: "Не удалось определить дальнейший шаг сценария поиска рейса."
              },
              :emit_failed_response
            )
          end
        end

        def ask_missing(state)
          {
            response: partial_response(
              state.fetch(:req),
              state[:collect_prompt],
              active_workflow_id: state[:current_scenario_id],
              pending: Runtime::Util.extract_hash(state[:collect_pending])
            )
          }
        end

        def call_status_tool(state, await)
          req = state.fetch(:req)
          args = Runtime::Util.extract_hash(state[:collected_params])
          tool_resp = await.call(
            "flight_lookup",
            :tool,
            tool_name: TOOL_NAME,
            args: args
          )

          unless tool_resp[:ok]
            code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
            code = "tool_failed" if code.empty?
            if code == "not_found"
              return {
                response_message: "Статус рейса не найден.",
                tool_status: "not_found"
              }
            end

            failure_message = "Не удалось получить статус рейса."
            return {
              error_code: code,
              error_message: failure_message,
              error_client_handler: {
                command: "SHOW_ERROR_MESSAGE",
                payload: { message: failure_message, code: code }
              },
              tool_status: "failed"
            }
          end

          final_resp = await.call(
            "flight_response",
            :llm,
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
          message = extract_llm_text(final_resp)
          message = fallback_flight_status_message(tool_resp[:data]) if message.to_s.empty?
          message = "Готово." if message.to_s.empty?

          {
            response_message: message,
            tool_status: "done"
          }
        end

        def route_after_tool(state)
          case state[:tool_status]
          when "done"
            AsyncGraph::Command.goto(:emit_final_response)
          when "not_found"
            AsyncGraph::Command.goto(:emit_not_found_response)
          when "failed"
            AsyncGraph::Command.goto(:emit_failed_response)
          else
            AsyncGraph::Command.update_and_goto(
              {
                error_code: "flight_lookup_failed",
                error_message: "Не удалось завершить сценарий поиска рейса."
              },
              :emit_failed_response
            )
          end
        end

        def emit_final_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        def emit_not_found_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        def emit_failed_response(state)
          code = state[:error_code].to_s
          code = "workflow_failed" if code.empty?
          message = state[:error_message].to_s
          message = "Workflow failed." if message.empty?

          {
            response: failed_response(
              state.fetch(:req),
              code: code,
              message: message,
              client_handler: state[:error_client_handler]
            )
          }
        end

        def reroute(state)
          response = state.fetch(:scenario_runner).call(state[:reroute_scenario_id], state)
          { response: response }
        end

        private

        def normalize_tool_params(resp)
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          extracted = data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
          prompt = data[:prompt]
          prompt = prompt.to_s unless prompt.nil? || prompt.is_a?(String)
          { extracted: extracted, prompt: prompt }
        end

        def merge_non_empty_params(base, new_values)
          merged = Runtime::Util.extract_hash(base)
          Runtime::Util.extract_hash(new_values).each do |key, value|
            next if value.nil?
            next if value.is_a?(String) && value.strip.empty?

            merged[key] = value
          end
          merged
        end

        def ready_with_any_field?(payload, fields)
          Array(fields).map(&:to_sym).any? do |key|
            value = payload[key]
            value.is_a?(String) ? !value.strip.empty? : !value.nil?
          end
        end

        def filtered_router_scenarios(state, excluded_scenario_id)
          excluded = excluded_scenario_id.to_s
          Array(state[:router_scenarios]).filter_map do |item|
            entry = Runtime::Util.extract_hash(item)
            next if entry[:id].to_s == excluded

            { id: entry[:id].to_s, description: entry[:description].to_s }
          end
        end

        def normalize_routing_choice(resp, available_scenarios)
          allowed_ids = available_scenarios.map { |item| item[:id].to_s }
          data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
          candidate = data[:workflow_id].to_s.strip
          return candidate if allowed_ids.include?(candidate)

          Runtime::ScenarioIds::FREE_SPEECH
        end

        def fallback_flight_status_message(tool_data)
          data = extract_nested_data(tool_data) || {}
          flight = data[:flight].is_a?(Hash) ? Runtime::Util.extract_hash(data[:flight]) : {}
          return "Статус рейса не найден." if flight.empty?

          flight_number = flight[:flight_number].to_s.strip
          flight_number = "рейс" if flight_number.empty?
          from = flight[:from].to_s.strip
          from = "?" if from.empty?
          to = flight[:to].to_s.strip
          to = "?" if to.empty?
          departure = compact_time(flight[:departure_time])
          arrival = compact_time(flight[:arrival_time])
          status = status_text(flight[:status].to_s)

          "Рейс #{flight_number} (#{from} → #{to}), вылет #{departure}, прибытие #{arrival}. Статус: #{status}."
        end

        def compact_time(value)
          text = value.to_s.strip
          return "?" if text.empty?
          return text[11, 5] if text.length >= 16 && text.include?("T")

          text
        end

        def status_text(value)
          status = value.to_s.strip.upcase
          return "неизвестен" if status.empty?

          {
            "ON_TIME" => "вовремя",
            "DELAYED" => "задерживается",
            "CANCELLED" => "отменен"
          }.fetch(status, status.downcase)
        end
      end
    end
  end
end

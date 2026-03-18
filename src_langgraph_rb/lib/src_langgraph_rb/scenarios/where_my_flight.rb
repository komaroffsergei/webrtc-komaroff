# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module WhereMyFlight
      module_function

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

      def register(builder)
        builder.scenario("where_my_flight@2.0.0") do
          title "Where My Flight"
          description "Collect flight lookup params and shape the follow-up response"
          routing_description "Найти статус рейса по номеру рейса или фамилии пассажира"
          tags :flight, :lookup
          capabilities :pending_params, :tool_params, :tool_call, :handoff
          required_tools :get_flight_status
          runtime_flags pending_key: :flight_lookup, active_workflow_id: "where_my_flight@2.0.0"

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :collect_params

            node :collect_params, kind: :compute, op: :collect_tool_params_with_pending, task: TOOL_PARAMS_TASK,
              tool_name: TOOL_NAME, tool_schema: TOOL_SCHEMA, ask_input_default: ASK_INPUT_DEFAULT,
              ready_if_any_present: %i[flight_number last_name], pending_missing: ["flight_number_or_last_name"],
              pending_scenario_id: "where_my_flight@2.0.0", followup_pattern: FOLLOWUP_RE,
              status_key: :flight_param_status, merged_key: :merged_params, prompt_key: :response_prompt,
              pending_key: :pending_state, excluded_scenarios: ["where_my_flight@2.0.0"]
            node :ask_missing, kind: :partial_response, pending_key: :flight_lookup
            node :call_status_tool, kind: :compute, op: :tool_lookup_with_llm_response, tool_name: TOOL_NAME,
              args_source: :merged_params, task: FINAL_TASK, scenario_context: SCENARIO_CONTEXT,
              status_key: :flight_tool_result_status, not_found_code: "not_found",
              not_found_message: "Статус рейса не найден.", failure_message: "Не удалось получить статус рейса.",
              fallback_formatter: :flight_status
            node :tool_not_found, kind: :done_response, message_source: :response_message
            node :tool_failed, kind: :failed_response, message_source: :error_message
            node :reroute, kind: :compute, op: :reroute_selected_scenario, scenario_source: :reroute_scenario_id

            conditional_edge :collect_params, :flight_param_status, {
              "ready" => :call_status_tool,
              "missing" => :ask_missing,
              "reroute" => :reroute
            }

            edge :ask_missing, ref(:terminal, :respond)
            conditional_edge :call_status_tool, :flight_tool_result_status, {
              "done" => ref(:final, :respond),
              "not_found" => :tool_not_found,
              "failed" => :tool_failed
            }
            edge :tool_not_found, ref(:terminal, :respond)
            edge :tool_failed, ref(:terminal, :respond)
            edge :reroute, ref(:terminal, :respond)
          end
        end
      end
    end
  end
end

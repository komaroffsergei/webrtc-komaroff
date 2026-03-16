# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module WhereMyFlight
      module_function

      def register(builder)
        builder.scenario("where_my_flight@2.0.0") do
          title "Where My Flight"
          description "Collect flight lookup params and shape the follow-up response"
          tags :flight, :lookup
          capabilities :pending_params, :tool_params, :tool_call, :handoff
          required_tools :get_flight_status
          runtime_flags pending_key: :flight_lookup, active_workflow_id: "where_my_flight@2.0.0"

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :collect_params

            node :collect_params, kind: :flight_collect_params, tool_name: :get_flight_status
            node :ask_missing, kind: :partial_response, pending_key: :flight_lookup
            node :call_status_tool, kind: :flight_lookup_tool, tool_name: :get_flight_status
            node :tool_not_found, kind: :done_response, message_source: :response_message
            node :tool_failed, kind: :failed_response, message_source: :error_message
            node :reroute, kind: :flight_reroute

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

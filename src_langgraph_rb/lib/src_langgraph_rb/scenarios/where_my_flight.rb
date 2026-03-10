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
            entry_point :collect_params

            node :collect_params, kind: :llm_tool_params, tool_name: :get_flight_status
            node :ask_missing, kind: :partial_response, pending_key: :flight_lookup
            node :call_status_tool, kind: :tool_call, tool_name: :get_flight_status
            node :reroute, kind: :scenario_handoff

            conditional_edge :collect_params, :flight_param_status, {
              "ready" => :call_status_tool,
              "missing" => :ask_missing,
              "reroute" => :reroute
            }

            edge :call_status_tool, ref(:final, :respond)
            finish_point :ask_missing
            finish_point :reroute
          end
        end
      end
    end
  end
end

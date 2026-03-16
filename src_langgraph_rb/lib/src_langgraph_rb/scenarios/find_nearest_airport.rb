# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module FindNearestAirport
      module_function

      def register(builder)
        builder.scenario("find_nearest_airport@2.0.0") do
          title "Find Nearest Airport"
          description "Resolve position, search airports, build a route, and respond"
          tags :airport, :geo
          capabilities :tool_params, :tool_call, :client_events
          required_tools :get_current_position, :search_airports_nearby, :build_route
          runtime_flags context_required: true, artifact_memory: true

          graph do
            use :assistant_reply_tail, as: :final
            use :state_response_tail, as: :terminal
            entry_point :get_position

            node :get_position, kind: :tool_call, tool_name: :get_current_position, args_source: :empty_args, result_key: :position_response,
              failure_message: "Не удалось получить текущую позицию."
            node :position_failed, kind: :failed_response, message_source: :error_message
            node :prepare_airport_search, kind: :airport_prepare_search
            node :search_airports, kind: :tool_call, tool_name: :search_airports_nearby, args_source: :search_args, result_key: :search_response,
              failure_message: "Не удалось найти ближайшие аэропорты."
            node :search_failed, kind: :failed_response, message_source: :error_message
            node :prepare_route, kind: :airport_prepare_route
            node :route_args_failed, kind: :failed_response, message_source: :error_message
            node :build_route, kind: :airport_build_route, tool_name: :build_route
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

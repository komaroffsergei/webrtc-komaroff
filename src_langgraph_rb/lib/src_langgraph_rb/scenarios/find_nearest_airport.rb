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
            entry_point :get_position

            node :get_position, kind: :tool_call, tool_name: :get_current_position
            node :prepare_airport_search, kind: :llm_tool_params, tool_name: :search_airports_nearby
            node :search_airports, kind: :tool_call, tool_name: :search_airports_nearby
            node :prepare_route, kind: :llm_tool_params, tool_name: :build_route
            node :build_route, kind: :tool_call, tool_name: :build_route

            edge :get_position, :prepare_airport_search
            edge :prepare_airport_search, :search_airports
            edge :search_airports, :prepare_route
            edge :prepare_route, :build_route
            edge :build_route, ref(:final, :respond)
          end
        end
      end
    end
  end
end

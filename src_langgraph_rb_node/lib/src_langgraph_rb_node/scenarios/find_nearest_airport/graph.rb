# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module FindNearestAirport
      class Graph
        def self.build
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            node :get_position, &nodes.method(:get_position)
            node :route_after_position, &nodes.method(:route_after_position)
            node :prepare_airport_search, &nodes.method(:prepare_airport_search)
            node :search_airports, &nodes.method(:search_airports)
            node :route_after_search, &nodes.method(:route_after_search)
            node :prepare_route, &nodes.method(:prepare_route)
            node :route_after_route_args, &nodes.method(:route_after_route_args)
            node :build_route, &nodes.method(:build_route)
            node :route_after_build_route, &nodes.method(:route_after_build_route)
            node :emit_final_response, &nodes.method(:emit_final_response)
            node :position_failed, &nodes.method(:position_failed)
            node :search_failed, &nodes.method(:search_failed)
            node :route_args_failed, &nodes.method(:route_args_failed)
            node :build_route_failed, &nodes.method(:build_route_failed)

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
      end
    end
  end
end

# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      class Graph
        def self.build
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            node :collect_params, &nodes.method(:collect_params)
            node :route_after_collect, &nodes.method(:route_after_collect)
            node :ask_missing, &nodes.method(:ask_missing)
            node :call_status_tool, &nodes.method(:call_status_tool)
            node :route_after_tool, &nodes.method(:route_after_tool)
            node :emit_final_response, &nodes.method(:emit_final_response)
            node :emit_not_found_response, &nodes.method(:emit_not_found_response)
            node :emit_failed_response, &nodes.method(:emit_failed_response)
            node :reroute, &nodes.method(:reroute)

            set_entry_point :collect_params
            edge :collect_params, :route_after_collect
            edge :call_status_tool, :route_after_tool
            set_finish_point :ask_missing
            set_finish_point :emit_final_response
            set_finish_point :emit_not_found_response
            set_finish_point :emit_failed_response
            set_finish_point :reroute
          end
        end
      end
    end
  end
end

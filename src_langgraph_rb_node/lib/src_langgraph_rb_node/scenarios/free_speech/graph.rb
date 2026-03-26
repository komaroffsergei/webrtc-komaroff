# frozen_string_literal: true

require_relative "nodes"

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      class Graph
        def self.build
          nodes = Nodes.new

          AsyncGraph::Graph.new do
            node :prepare_context, &nodes.method(:prepare_context)
            node :route_after_prepare, &nodes.method(:route_after_prepare)
            node :clarify_reference, &nodes.method(:clarify_reference)
            node :compose_response, &nodes.method(:compose_response)
            node :emit_final_response, &nodes.method(:emit_final_response)

            set_entry_point :prepare_context
            edge :prepare_context, :route_after_prepare
            edge :compose_response, :emit_final_response
            set_finish_point :clarify_reference
            set_finish_point :emit_final_response
          end
        end
      end
    end
  end
end

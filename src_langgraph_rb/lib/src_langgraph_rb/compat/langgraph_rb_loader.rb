# frozen_string_literal: true

module SrcLanggraphRb
  module Compat
    module LanggraphRbLoader
      module_function

      def load!
        return if defined?(::LangGraphRB::Graph)

        define_base_errors!
        require "langgraph_rb/state"
        require "langgraph_rb/node"
        require "langgraph_rb/edge"
        require "langgraph_rb/graph"
      end

      def define_base_errors!
        return if defined?(::LangGraphRB::Error)

        graph_module = if defined?(::LangGraphRB)
          ::LangGraphRB
        else
          Object.const_set(:LangGraphRB, Module.new)
        end

        error_class = graph_module.const_set(:Error, Class.new(StandardError))
        graph_module.const_set(:GraphError, Class.new(error_class))
        graph_module.const_set(:NodeError, Class.new(error_class))
        graph_module.const_set(:StateError, Class.new(error_class))
      end
      private_class_method :define_base_errors!
    end
  end
end

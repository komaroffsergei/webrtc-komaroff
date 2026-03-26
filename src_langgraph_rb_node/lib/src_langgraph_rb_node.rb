# frozen_string_literal: true

require "async-graph"

require_relative "src_langgraph_rb_node/version"
require_relative "src_langgraph_rb_node/errors"
require_relative "src_langgraph_rb_node/scenario_definition"
require_relative "src_langgraph_rb_node/registry"
require_relative "src_langgraph_rb_node/runtime/util"
require_relative "src_langgraph_rb_node/runtime/contracts/common"
require_relative "src_langgraph_rb_node/runtime/contracts/workflow"
require_relative "src_langgraph_rb_node/runtime/contracts/llm"
require_relative "src_langgraph_rb_node/runtime/contracts/tools"
require_relative "src_langgraph_rb_node/runtime/responses"
require_relative "src_langgraph_rb_node/runtime/memory"
require_relative "src_langgraph_rb_node/runtime/runtime_io"
require_relative "src_langgraph_rb_node/runtime/request_executor"
require_relative "src_langgraph_rb_node/runtime/graph_runner"
require_relative "src_langgraph_rb_node/runtime/scenario_ids"
require_relative "src_langgraph_rb_node/runtime/router"
require_relative "src_langgraph_rb_node/runtime/engine"
require_relative "src_langgraph_rb_node/runtime/service"
require_relative "src_langgraph_rb_node/scenarios/base_nodes"
require_relative "src_langgraph_rb_node/scenarios/free_speech/definition"
require_relative "src_langgraph_rb_node/scenarios/where_my_flight/definition"
require_relative "src_langgraph_rb_node/scenarios/find_nearest_airport/definition"
require_relative "src_langgraph_rb_node/scenarios/built_in_registry"

module SrcLanggraphRbNode
  class << self
    def built_in_registry
      Scenarios::BuiltInRegistry.build
    end
  end
end

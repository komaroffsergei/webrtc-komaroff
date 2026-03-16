# frozen_string_literal: true

require_relative "src_langgraph_rb/version"
require_relative "src_langgraph_rb/errors"
require_relative "src_langgraph_rb/contracts/validation"
require_relative "src_langgraph_rb/contracts/common"
require_relative "src_langgraph_rb/contracts/workflow"
require_relative "src_langgraph_rb/contracts/llm"
require_relative "src_langgraph_rb/contracts/tools"
require_relative "src_langgraph_rb/schema/node"
require_relative "src_langgraph_rb/schema/edge"
require_relative "src_langgraph_rb/schema/fragment_import"
require_relative "src_langgraph_rb/schema/fragment"
require_relative "src_langgraph_rb/schema/graph"
require_relative "src_langgraph_rb/schema/scenario_metadata"
require_relative "src_langgraph_rb/schema/scenario"
require_relative "src_langgraph_rb/validation/rules"
require_relative "src_langgraph_rb/catalog"
require_relative "src_langgraph_rb/catalog/builder"
require_relative "src_langgraph_rb/dsl/support/identifiers"
require_relative "src_langgraph_rb/dsl/support/normalization"
require_relative "src_langgraph_rb/dsl/support/fragment_importer"
require_relative "src_langgraph_rb/dsl/fragment_builder"
require_relative "src_langgraph_rb/dsl/graph_builder"
require_relative "src_langgraph_rb/dsl/scenario_builder"
require_relative "src_langgraph_rb/compat/langgraph_rb_loader"
require_relative "src_langgraph_rb/adapters/lang_graph_rb/builder_plan"
require_relative "src_langgraph_rb/runtime/util"
require_relative "src_langgraph_rb/runtime/contracts/common"
require_relative "src_langgraph_rb/runtime/contracts/workflow"
require_relative "src_langgraph_rb/runtime/contracts/llm"
require_relative "src_langgraph_rb/runtime/contracts/tools"
require_relative "src_langgraph_rb/runtime/scenario_ids"
require_relative "src_langgraph_rb/runtime/config_loader"
require_relative "src_langgraph_rb/runtime/responses"
require_relative "src_langgraph_rb/runtime/memory"
require_relative "src_langgraph_rb/runtime/scenarios/common"
require_relative "src_langgraph_rb/runtime/scenarios/free_speech"
require_relative "src_langgraph_rb/runtime/scenarios/where_my_flight"
require_relative "src_langgraph_rb/runtime/scenarios/find_nearest_airport"
require_relative "src_langgraph_rb/runtime/router"
require_relative "src_langgraph_rb/runtime/settings"
require_relative "src_langgraph_rb/runtime/runtime_io"
require_relative "src_langgraph_rb/runtime/engine"
require_relative "src_langgraph_rb/runtime/service"
require_relative "src_langgraph_rb/scenarios/shared_fragments"
require_relative "src_langgraph_rb/scenarios/free_speech"
require_relative "src_langgraph_rb/scenarios/where_my_flight"
require_relative "src_langgraph_rb/scenarios/find_nearest_airport"
require_relative "src_langgraph_rb/scenarios/built_in_catalog"

module SrcLanggraphRb
  class << self
    def build_catalog(&block)
      Catalog.build(&block)
    end

    def built_in_catalog
      Scenarios::BuiltInCatalog.build
    end
  end
end

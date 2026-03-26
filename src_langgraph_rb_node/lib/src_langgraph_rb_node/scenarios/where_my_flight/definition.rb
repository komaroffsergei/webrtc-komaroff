# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      module_function

      def definition
        ScenarioDefinition.new(
          id: Runtime::ScenarioIds::WHERE_MY_FLIGHT,
          metadata: ScenarioMetadata.new(
            title: "Where My Flight",
            description: "Collect flight lookup params and shape the follow-up response",
            routing_description: "Найти статус рейса по номеру рейса или фамилии пассажира",
            tags: %i[flight lookup]
          ),
          graph: Graph.build
        )
      end
    end
  end
end

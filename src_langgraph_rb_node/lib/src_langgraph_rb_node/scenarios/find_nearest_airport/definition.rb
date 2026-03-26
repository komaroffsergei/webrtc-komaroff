# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module FindNearestAirport
      module_function

      def definition
        ScenarioDefinition.new(
          id: Runtime::ScenarioIds::FIND_NEAREST_AIRPORT,
          metadata: ScenarioMetadata.new(
            title: "Find Nearest Airport",
            description: "Resolve position, search airports, build a route, and respond",
            routing_description: "Найти ближайший аэропорт и построить маршрут до него",
            tags: %i[airport geo]
          ),
          graph: Graph.build
        )
      end
    end
  end
end

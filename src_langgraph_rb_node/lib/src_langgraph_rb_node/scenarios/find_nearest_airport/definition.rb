# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module FindNearestAirport
      module_function

      # Собирает описание сценария поиска ближайшего аэропорта.
      # Это описание использует registry/router для выбора сценария и графа выполнения.
      def definition
        ScenarioDefinition.new(
          # Стабильный идентификатор сценария в runtime.
          id: Runtime::ScenarioIds::FIND_NEAREST_AIRPORT,
          metadata: ScenarioMetadata.new(
            # Короткое имя сценария для разработчика и внутренних списков.
            title: "Find Nearest Airport",
            # Техническое описание полного пайплайна сценария.
            description: "Resolve position, search airports, build a route, and respond",
            # Фраза для LLM-router, чтобы он выбирал этот сценарий по смыслу запроса.
            routing_description: "Найти ближайший аэропорт и построить маршрут до него",
            # Семантические теги для категоризации сценария.
            tags: %i[airport geo]
          ),
          # Граф строится отдельным builder-классом.
          graph: Graph.build
        )
      end
    end
  end
end

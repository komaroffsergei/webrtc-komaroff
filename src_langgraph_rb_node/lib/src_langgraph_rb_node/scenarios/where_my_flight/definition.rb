# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module WhereMyFlight
      module_function

      # Собирает описание сценария поиска статуса рейса.
      # Definition используется registry и router-слоем для выбора workflow.
      def definition
        ScenarioDefinition.new(
          # Стабильный ID сценария.
          id: Runtime::ScenarioIds::WHERE_MY_FLIGHT,
          metadata: ScenarioMetadata.new(
            # Название сценария для человека.
            title: "Where My Flight",
            # Техническое описание внутреннего поведения.
            description: "Collect flight lookup params and shape the follow-up response",
            # Описание для LLM-router на русском языке.
            routing_description: "Найти статус рейса по номеру рейса или фамилии пассажира",
            # Теги сценария.
            tags: %i[flight lookup]
          ),
          # Построенный граф сценария.
          graph: Graph.build
        )
      end
    end
  end
end

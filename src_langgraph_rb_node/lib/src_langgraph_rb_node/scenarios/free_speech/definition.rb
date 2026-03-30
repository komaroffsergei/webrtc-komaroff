# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      module_function

      # Собирает описание сценария свободного диалога.
      # Это fallback-сценарий, который отвечает без инструментов.
      def definition
        ScenarioDefinition.new(
          # Стабильный идентификатор сценария в runtime.
          id: Runtime::ScenarioIds::FREE_SPEECH,
          metadata: ScenarioMetadata.new(
            # Отображаемое имя сценария.
            title: "Free Speech",
            # Короткое техническое описание поведения.
            description: "Generic free-form dialog without tools",
            # Формулировка для семантического роутинга запросов.
            routing_description: "Свободный разговор: общение с пользователем без инструментов",
            # Теги для категоризации как fallback/chat сценария.
            tags: %i[chat fallback]
          ),
          # Граф выполнения сценария.
          graph: Graph.build
        )
      end
    end
  end
end

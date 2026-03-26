# frozen_string_literal: true

require_relative "graph"

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      module_function

      def definition
        ScenarioDefinition.new(
          id: Runtime::ScenarioIds::FREE_SPEECH,
          metadata: ScenarioMetadata.new(
            title: "Free Speech",
            description: "Generic free-form dialog without tools",
            routing_description: "Свободный разговор: общение с пользователем без инструментов",
            tags: %i[chat fallback]
          ),
          graph: Graph.build
        )
      end
    end
  end
end

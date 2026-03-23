# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module BuiltInRegistry
      module_function

      def build
        Registry.new(
          scenarios: [
            FreeSpeech.definition,
            WhereMyFlight.definition,
            FindNearestAirport.definition
          ]
        )
      end
    end
  end
end

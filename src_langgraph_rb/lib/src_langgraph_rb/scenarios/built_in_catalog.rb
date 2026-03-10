# frozen_string_literal: true

module SrcLanggraphRb
  module Scenarios
    module BuiltInCatalog
      module_function

      def build
        SrcLanggraphRb.build_catalog do
          SharedFragments.register(self)
          FreeSpeech.register(self)
          WhereMyFlight.register(self)
          FindNearestAirport.register(self)
        end
      end
    end
  end
end

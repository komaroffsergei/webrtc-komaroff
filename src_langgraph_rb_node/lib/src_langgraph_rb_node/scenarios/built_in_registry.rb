# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    # Реестр встроенных сценариев, доступных в Ruby node-реализации.
    # Этот модуль нужен, чтобы собрать единый Registry из всех scenario definitions.
    module BuiltInRegistry
      module_function

      # Возвращает Registry со всеми встроенными сценариями.
      # Порядок элементов здесь отражает порядок их регистрации.
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

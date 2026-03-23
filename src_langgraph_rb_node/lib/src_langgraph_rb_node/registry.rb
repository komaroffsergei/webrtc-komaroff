# frozen_string_literal: true

module SrcLanggraphRbNode
  class Registry
    def initialize(scenarios:)
      @scenarios = {}
      Array(scenarios).each do |scenario|
        register(scenario)
      end
    end

    def register(scenario)
      raise ValidationError, "Scenario must be a ScenarioDefinition" unless scenario.is_a?(ScenarioDefinition)
      raise RegistryError, "Scenario '#{scenario.id}' is already registered" if @scenarios.key?(scenario.id)

      @scenarios[scenario.id] = scenario
    end

    def fetch(id)
      key = id.to_s
      @scenarios.fetch(key) do
        raise RegistryError, "Scenario '#{key}' is not registered in src_langgraph_rb_node"
      end
    end

    def include?(id)
      @scenarios.key?(id.to_s)
    end

    def all
      @scenarios.values.freeze
    end
  end
end

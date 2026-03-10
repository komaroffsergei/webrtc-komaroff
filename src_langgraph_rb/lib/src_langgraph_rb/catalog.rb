# frozen_string_literal: true

module SrcLanggraphRb
  class Catalog
    def self.build(&block)
      Catalog::Builder.build(&block)
    end

    def initialize(scenarios:, fragments:)
      @scenarios = scenarios.freeze
      @fragments = fragments.freeze
    end

    def fetch(id)
      @scenarios.fetch(id.to_s) do
        raise RegistryError, "Scenario '#{id}' is not registered"
      end
    end

    def all
      @scenarios.values.sort_by(&:id)
    end

    def filter(tags: nil, capabilities: nil)
      requested_tags = Array(tags).map(&:to_s)
      requested_capabilities = Array(capabilities).map(&:to_s)

      all.select do |scenario|
        tags_ok = requested_tags.empty? || (requested_tags - scenario.metadata.tags.map(&:to_s)).empty?
        capabilities_ok = requested_capabilities.empty? || (requested_capabilities - scenario.metadata.capabilities.map(&:to_s)).empty?
        tags_ok && capabilities_ok
      end
    end

    def to_builder_plan(id)
      Adapters::LangGraphRB::BuilderPlan.from_spec(fetch(id))
    end

    def to_h
      {
        scenarios: all.map(&:to_h),
        fragments: @fragments.values.sort_by(&:name).map(&:to_h)
      }
    end

    def fragment(name)
      @fragments.fetch(name.to_s) do
        raise RegistryError, "Fragment '#{name}' is not registered"
      end
    end
  end
end

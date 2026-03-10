# frozen_string_literal: true

module SrcLanggraphRb
  class Catalog
    class Builder
      def self.build(&block)
        builder = new
        builder.instance_eval(&block) if block
        builder.build
      end

      def initialize
        @fragments = {}
        @scenarios = {}
      end

      def fragment(name, &block)
        spec = DSL::FragmentBuilder.build(name, &block)
        key = spec.name.to_s
        raise RegistryError, "Fragment '#{key}' is already registered" if @fragments.key?(key)

        @fragments[key] = spec
        spec
      end

      def scenario(id, &block)
        spec = DSL::ScenarioBuilder.build(id, fragment_lookup: method(:fetch_fragment), &block)
        raise RegistryError, "Scenario '#{spec.id}' is already registered" if @scenarios.key?(spec.id)

        @scenarios[spec.id] = spec
        spec
      end

      def build
        Catalog.new(
          scenarios: @scenarios.dup,
          fragments: @fragments.dup
        )
      end

      def fetch_fragment(name)
        @fragments.fetch(name.to_s) do
          raise FragmentError, "Fragment '#{name}' is not registered"
        end
      end
    end
  end
end

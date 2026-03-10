# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    class ScenarioBuilder
      def self.build(id, fragment_lookup:, &block)
        builder = new(id, fragment_lookup:)
        builder.instance_eval(&block) if block
        builder.build
      end

      def initialize(id, fragment_lookup:)
        @id = id.to_s
        @fragment_lookup = fragment_lookup
        @title = nil
        @description = nil
        @tags = []
        @capabilities = []
        @required_tools = []
        @runtime_flags = {}
        @graph_builder = nil
      end

      def title(value)
        @title = value.to_s.strip
      end

      def description(value)
        @description = value.to_s.strip
      end

      def tags(*values)
        @tags.concat(clean_values(values))
      end

      def capabilities(*values)
        @capabilities.concat(clean_values(values))
      end

      def required_tools(*values)
        @required_tools.concat(clean_values(values))
      end

      def runtime_flags(**values)
        values.each do |key, value|
          @runtime_flags[key.to_sym] = value
        end
      end

      def graph(&block)
        @graph_builder = GraphBuilder.new(fragment_lookup: @fragment_lookup)
        @graph_builder.instance_eval(&block) if block
      end

      def build
        raise ValidationError, "Scenario '#{@id}' must define a graph" unless @graph_builder

        metadata = Schema::ScenarioMetadata.new(
          @title,
          @description,
          @tags.uniq.freeze,
          @capabilities.uniq.freeze,
          @required_tools.uniq.freeze,
          @runtime_flags.dup.freeze
        )

        Schema::Scenario.new(@id, metadata, @graph_builder.build).validate!
      end

      private

      def clean_values(values)
        values.flatten.map { |value| value.to_s.strip }.reject(&:empty?)
      end
    end
  end
end

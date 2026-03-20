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
        @routing_description = nil
        @tags = []
        @capabilities = []
        @required_tools = []
        @runtime_flags = {}
        @tool_profiles = {}
        @graph_block = nil
      end

      def title(value)
        @title = value.to_s.strip
      end

      def description(value)
        @description = value.to_s.strip
      end

      def routing_description(value)
        @routing_description = value.to_s.strip
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

      def tool_profile(name, **values)
        key = name.to_s.strip
        raise ValidationError, "Tool profile name must be provided" if key.empty?
        raise ValidationError, "Tool profile '#{key}' is already registered in scenario '#{@id}'" if @tool_profiles.key?(key)

        @tool_profiles[key] = Support::Normalization.normalize_hash(values)
      end

      def graph(&block)
        @graph_block = block
      end

      def build
        raise ValidationError, "Scenario '#{@id}' must define a graph" unless @graph_block

        graph_builder = GraphBuilder.new(
          fragment_lookup: @fragment_lookup,
          tool_profiles: @tool_profiles,
          scenario_id: @id
        )
        graph_builder.instance_eval(&@graph_block)

        required_tools = (@required_tools + graph_builder.required_tools.to_a).uniq
        runtime_flags = @runtime_flags.dup
        if graph_builder.pending_enabled?
          runtime_flags[:pending_key] ||= graph_builder.pending_key
          runtime_flags[:active_workflow_id] ||= @id
        end

        metadata = Schema::ScenarioMetadata.new(
          @title,
          @description,
          @routing_description,
          @tags.uniq.freeze,
          @capabilities.uniq.freeze,
          required_tools.freeze,
          runtime_flags.freeze
        )

        Schema::Scenario.new(@id, metadata, graph_builder.build).validate!
      end

      private

      def clean_values(values)
        values.flatten.map { |value| value.to_s.strip }.reject(&:empty?)
      end
    end
  end
end

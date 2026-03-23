# frozen_string_literal: true

module SrcLanggraphRbNode
  class ScenarioMetadata
    attr_reader :title, :description, :routing_description, :tags

    def initialize(title:, description:, routing_description:, tags: [])
      @title = title.to_s.strip
      @description = description.to_s.strip
      @routing_description = routing_description.to_s.strip
      @tags = Array(tags).map(&:to_s).reject(&:empty?).freeze
      validate!
    end

    private

    def validate!
      raise ValidationError, "Scenario title must be provided" if title.empty?
      raise ValidationError, "Scenario description must be provided" if description.empty?
      raise ValidationError, "Scenario routing_description must be provided" if routing_description.empty?
    end
  end

  class ScenarioDefinition
    attr_reader :id, :metadata, :graph

    def initialize(id:, metadata:, graph:)
      @id = id.to_s.strip
      @metadata = metadata
      @graph = graph
      validate!
    end

    def routing_entry
      { id: id, description: metadata.routing_description }
    end

    private

    def validate!
      raise ValidationError, "Scenario id must be provided" if id.empty?
      raise ValidationError, "Scenario metadata must be a ScenarioMetadata" unless metadata.is_a?(ScenarioMetadata)
      raise ValidationError, "Scenario graph must be an AsyncGraph::Graph" unless defined?(AsyncGraph::Graph) && graph.is_a?(AsyncGraph::Graph)

      graph.validate!
    end
  end
end

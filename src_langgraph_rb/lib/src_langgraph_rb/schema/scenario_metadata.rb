# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    ScenarioMetadata = Data.define(:title, :description, :routing_description, :tags, :capabilities, :required_tools, :runtime_flags) do
      def to_h
        {
          title: title,
          description: description,
          routing_description: routing_description,
          tags: tags.map(&:to_s),
          capabilities: capabilities.map(&:to_s),
          required_tools: required_tools.map(&:to_s),
          runtime_flags: runtime_flags
        }
      end
    end
  end
end

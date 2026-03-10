# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    ScenarioMetadata = Data.define(:title, :description, :tags, :capabilities, :required_tools, :runtime_flags) do
      def to_h
        {
          title: title,
          description: description,
          tags: tags.map(&:to_s),
          capabilities: capabilities.map(&:to_s),
          required_tools: required_tools.map(&:to_s),
          runtime_flags: runtime_flags
        }
      end
    end
  end
end

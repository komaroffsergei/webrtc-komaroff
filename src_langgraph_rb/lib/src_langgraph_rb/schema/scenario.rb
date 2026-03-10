# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    Scenario = Data.define(:id, :metadata, :graph) do
      def validate!
        Validation::Rules.validate_scenario!(self)
        self
      end

      def to_h
        {
          id: id,
          metadata: metadata.to_h,
          graph: graph.to_h
        }
      end
    end
  end
end

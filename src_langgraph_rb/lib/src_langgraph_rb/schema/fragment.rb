# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    Fragment = Data.define(:name, :nodes, :edges, :finish_points, :defaults) do
      def validate!
        Validation::Rules.validate_fragment!(self)
        self
      end

      def to_h
        {
          name: name.to_s,
          nodes: nodes.map(&:to_h),
          edges: edges.map(&:to_h),
          finish_points: finish_points.map(&:to_s),
          defaults: defaults
        }
      end
    end
  end
end

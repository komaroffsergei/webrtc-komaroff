# frozen_string_literal: true

module SrcLanggraphRb
  module Schema
    Graph = Data.define(:entry_point, :finish_points, :nodes, :edges, :defaults, :imports) do
      def to_h
        {
          entry_point: entry_point.to_s,
          finish_points: finish_points.map(&:to_s),
          nodes: nodes.map(&:to_h),
          edges: edges.map(&:to_h),
          defaults: defaults,
          imports: imports.map(&:to_h)
        }
      end
    end
  end
end

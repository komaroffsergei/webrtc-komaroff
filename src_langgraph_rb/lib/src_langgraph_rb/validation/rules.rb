# frozen_string_literal: true

require "set"

module SrcLanggraphRb
  module Validation
    module Rules
      module_function

      def validate_scenario!(scenario)
        raise ValidationError, "Scenario id must be provided" if scenario.id.to_s.strip.empty?

        graph = scenario.graph
        validate_graph!(graph)
      end

      def validate_fragment!(fragment)
        raise ValidationError, "Fragment name must be provided" if fragment.name.to_s.strip.empty?

        node_ids = fragment.nodes.map(&:id)
        ensure_unique_ids!(node_ids, "fragment node")
        fragment.finish_points.each { |node_id| ensure_node_exists!(node_id, node_ids, "fragment finish point") }
        validate_edges!(fragment.edges, node_ids)
      end

      def validate_graph!(graph)
        raise ValidationError, "Graph entry point must be provided" if graph.entry_point.to_s.strip.empty?
        raise ValidationError, "Graph must define at least one finish point" if graph.finish_points.empty?

        node_ids = graph.nodes.map(&:id)
        ensure_unique_ids!(node_ids, "node")
        ensure_node_exists!(graph.entry_point, node_ids, "entry point")
        graph.finish_points.each { |node_id| ensure_node_exists!(node_id, node_ids, "finish point") }
        validate_edges!(graph.edges, node_ids)
      end

      def validate_edges!(edges, node_ids)
        edges.each do |edge|
          ensure_node_exists!(edge.from, node_ids, "edge source")
          if edge.direct?
            ensure_node_exists!(edge.to, node_ids, "edge target")
            next
          end

          raise ValidationError, "Conditional edge router must be symbolic" if edge.router.to_s.strip.empty?
          raise ValidationError, "Conditional edge path map must not be empty" if edge.path_map.nil? || edge.path_map.empty?
          edge.path_map.each_value do |target_id|
            ensure_node_exists!(target_id, node_ids, "conditional edge target")
          end
        end
      end

      def ensure_unique_ids!(ids, label)
        seen = Set.new
        duplicates = Set.new
        ids.each do |id|
          duplicates << id if seen.include?(id)
          seen << id
        end
        return if duplicates.empty?

        raise ValidationError, "Duplicate #{label} ids: #{duplicates.to_a.map(&:to_s).sort.join(', ')}"
      end

      def ensure_node_exists!(node_id, node_ids, label)
        return if node_ids.include?(node_id)

        raise ValidationError, "#{label.capitalize} '#{node_id}' does not exist"
      end
    end
  end
end

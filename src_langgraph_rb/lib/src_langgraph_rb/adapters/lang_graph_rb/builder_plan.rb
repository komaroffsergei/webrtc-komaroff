# frozen_string_literal: true

module SrcLanggraphRb
  module Adapters
    module LangGraphRB
      class BuilderPlan
        def self.from_spec(spec)
          instructions = spec.graph.nodes.map do |node|
            {
              op: :node,
              id: node.id,
              kind: node.kind,
              config: node.config,
              meta: node.meta
            }
          end
          instructions << { op: :set_entry_point, id: spec.graph.entry_point }
          instructions.concat(build_edge_instructions(spec.graph.edges))
          spec.graph.finish_points.each do |node_id|
            instructions << { op: :set_finish_point, id: node_id }
          end

          new(spec:, instructions:)
        end

        def self.build_edge_instructions(edges)
          edges.map do |edge|
            if edge.direct?
              { op: :edge, from: edge.from, to: edge.to, meta: edge.meta }
            else
              {
                op: :conditional_edge,
                from: edge.from,
                router: edge.router,
                path_map: edge.path_map,
                meta: edge.meta
              }
            end
          end
        end
        private_class_method :build_edge_instructions

        attr_reader :spec, :instructions

        def initialize(spec:, instructions:)
          @spec = spec
          @instructions = instructions.freeze
        end

        def to_h
          {
            scenario_id: spec.id,
            instructions: instructions.map { |instruction| stringify(instruction) }
          }
        end

        def to_builder_block(node_resolver: nil, router_resolver: nil)
          plan = self
          proc do
            plan.instructions.each do |instruction|
              case instruction.fetch(:op)
              when :node
                callable = node_resolver ? node_resolver.call(instruction) : ->(_state, *_context) { {} }
                node(instruction.fetch(:id), callable)
              when :set_entry_point
                set_entry_point(instruction.fetch(:id))
              when :edge
                edge(instruction.fetch(:from), instruction.fetch(:to))
              when :conditional_edge
                router_callable = router_resolver ? router_resolver.call(instruction) : ->(_state) { nil }
                conditional_edge(instruction.fetch(:from), router_callable, instruction.fetch(:path_map))
              when :set_finish_point
                set_finish_point(instruction.fetch(:id))
              else
                raise ValidationError, "Unsupported builder instruction '#{instruction[:op]}'"
              end
            end
          end
        end

        def build_graph(state_class: nil, node_resolver: nil, router_resolver: nil)
          Compat::LanggraphRbLoader.load!
          actual_state_class = state_class || ::LangGraphRB::State
          ::LangGraphRB::Graph.new(
            state_class: actual_state_class,
            &to_builder_block(node_resolver:, router_resolver:)
          )
        end

        private

        def stringify(value)
          case value
          when Symbol
            value.to_s
          when Hash
            value.each_with_object({}) do |(key, item), out|
              out[key.to_s] = stringify(item)
            end
          when Array
            value.map { |item| stringify(item) }
          else
            value
          end
        end
      end
    end
  end
end

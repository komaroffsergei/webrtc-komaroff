# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    module Support
      module FragmentImporter
        module_function

        def import!(builder:, fragment:, as:)
          namespace = as.to_s.strip
          raise FragmentError, "Fragment alias must be provided" if namespace.empty?

          fragment.nodes.each do |node|
            builder.node(
              builder.ref(namespace, node.id),
              kind: node.kind,
              meta: node.meta,
              **node.config
            )
          end

          fragment.edges.each do |edge|
            if edge.direct?
              builder.edge(builder.ref(namespace, edge.from), builder.ref(namespace, edge.to), meta: edge.meta)
              next
            end

            builder.conditional_edge(
              builder.ref(namespace, edge.from),
              edge.router,
              edge.path_map.transform_values { |target| builder.ref(namespace, target) },
              meta: edge.meta
            )
          end

          fragment.finish_points.each do |node_id|
            builder.finish_point(builder.ref(namespace, node_id))
          end
          builder.merge_defaults(fragment.defaults)
          builder.register_import(fragment.name, namespace)
        end
      end
    end
  end
end

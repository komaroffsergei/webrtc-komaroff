# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    class GraphBuilder < FragmentBuilder
      def initialize(fragment_lookup:)
        super("__graph__")
        @fragment_lookup = fragment_lookup
        @entry_point = nil
        @imports = []
      end

      def entry_point(id)
        @entry_point = Support::Identifiers.normalize_id(id)
      end

      def use(name, as:)
        fragment = @fragment_lookup.call(name)
        Support::FragmentImporter.import!(builder: self, fragment:, as:)
      end

      def ref(namespace, node_name)
        Support::Identifiers.namespaced_id(namespace, node_name)
      end

      def register_import(name, alias_name)
        @imports << Schema::FragmentImport.new(name.to_s, Support::Identifiers.normalize_id(alias_name))
      end

      def build
        Schema::Graph.new(
          @entry_point,
          @finish_points.uniq.freeze,
          @nodes.dup.freeze,
          @edges.dup.freeze,
          @defaults.dup.freeze,
          @imports.dup.freeze
        )
      end
    end
  end
end

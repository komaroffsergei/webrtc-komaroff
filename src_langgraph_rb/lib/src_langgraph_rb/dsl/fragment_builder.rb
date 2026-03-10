# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    class FragmentBuilder
      def self.build(name, &block)
        builder = new(name)
        builder.instance_eval(&block) if block
        builder.build
      end

      attr_reader :name

      def initialize(name)
        @name = name.to_s
        @nodes = []
        @edges = []
        @finish_points = []
        @defaults = {}
      end

      def defaults(**values)
        merge_defaults(Support::Normalization.normalize_hash(values))
      end

      def node(id, kind: :local, meta: {}, **config)
        node_id = Support::Identifiers.normalize_id(id)
        if @nodes.any? { |existing| existing.id == node_id }
          raise ValidationError, "Node '#{node_id}' already exists in fragment '#{name}'"
        end

        @nodes << Schema::Node.new(
          node_id,
          Support::Identifiers.normalize_id(kind),
          Support::Normalization.normalize_hash(config),
          Support::Normalization.normalize_hash(meta)
        )
      end

      def edge(from, to, meta: {})
        @edges << Schema::Edge.new(
          :direct,
          Support::Identifiers.normalize_id(from),
          Support::Identifiers.normalize_id(to),
          nil,
          nil,
          Support::Normalization.normalize_hash(meta)
        )
      end

      def conditional_edge(from, router, path_map, meta: {})
        @edges << Schema::Edge.new(
          :conditional,
          Support::Identifiers.normalize_id(from),
          nil,
          Support::Identifiers.normalize_router(router),
          Support::Normalization.normalize_path_map(path_map),
          Support::Normalization.normalize_hash(meta)
        )
      end

      def finish_point(id)
        @finish_points << Support::Identifiers.normalize_id(id)
      end

      def merge_defaults(values)
        @defaults = @defaults.merge(values)
      end

      def build
        Schema::Fragment.new(
          @name,
          @nodes.dup.freeze,
          @edges.dup.freeze,
          @finish_points.uniq.freeze,
          @defaults.dup.freeze
        ).validate!
      end
    end
  end
end

# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    class GraphRunner
      def initialize(graph:, executor:)
        @graph = graph
        @executor = executor
        @fork_sequence = 0
      end

      def run(state:)
        @graph.validate!
        final_state = nil
        joins = {}
        queue = [build_token("root", @graph.entry, state)]

        until queue.empty?
          token = queue.shift
          if @graph.join?(token[:node]) && token[:from_node]
            join_result = @graph.process_join(token: token, joins: joins)
            joins = join_result.joins
            if join_result.parked?
              next
            else
              queue.unshift(join_result.token)
              next
            end
          end

          step = resolve_step(token)
          case step
          when AsyncGraph::Advanced
            final_state = enqueue_destinations(
              token: token,
              state: step.state,
              destinations: step.destinations,
              queue: queue,
              final_state: final_state
            )
          when AsyncGraph::Finished
            final_state = merge_final_state(final_state, step.state)
          else
            raise ValidationError, "Unsupported AsyncGraph step #{step.class}"
          end
        end

        raise ValidationError, "Graph run finished with unresolved joins" unless joins.empty?
        raise ValidationError, "Graph run did not produce a final state" if final_state.nil?

        final_state
      end

      private

      def build_token(token_uid, node, state, fork_uid: nil, branch: nil, from_node: nil)
        {
          token_uid: token_uid,
          node: node,
          state: state,
          fork_uid: fork_uid,
          branch: branch,
          from_node: from_node
        }
      end

      def resolve_step(token)
        resolved = {}

        loop do
          step = @graph.step(
            state: token[:state],
            node: token[:node],
            resolved: resolved
          )
          return step unless step.is_a?(AsyncGraph::Suspended)

          step.requests.each do |request|
            resolved[request.key.to_s] = @executor.call(request, state: token[:state])
          end
        end
      end

      def enqueue_destinations(token:, state:, destinations:, queue:, final_state:)
        if destinations.length <= 1
          edge = destinations.first
          return merge_final_state(final_state, state) if edge.to == AsyncGraph::FINISH

          queue << build_token(
            token[:token_uid],
            edge.to,
            state,
            fork_uid: token[:fork_uid],
            branch: token[:branch],
            from_node: token[:node]
          )
          return final_state
        end

        fork_uid = next_fork_uid
        destinations.each do |edge|
          if edge.to == AsyncGraph::FINISH
            final_state = merge_final_state(final_state, state)
            next
          end

          suffix = edge.branch || edge.to
          queue << build_token(
            "#{token[:token_uid]}.#{suffix}",
            edge.to,
            state,
            fork_uid: fork_uid,
            branch: edge.branch,
            from_node: token[:node]
          )
        end

        final_state
      end

      def next_fork_uid
        @fork_sequence += 1
        "fork-#{@fork_sequence}"
      end

      def merge_final_state(current, incoming)
        return incoming if current.nil?

        conflicts = (current.keys & incoming.keys).select { |key| current[key] != incoming[key] }
        raise AsyncGraph::JoinConflictError, "Final states conflict on keys: #{conflicts.join(', ')}" unless conflicts.empty?

        current.merge(incoming)
      end
    end
  end
end

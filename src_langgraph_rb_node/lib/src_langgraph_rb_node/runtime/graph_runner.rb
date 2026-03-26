# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    class GraphRunner
      def initialize(graph:, executor:, runner: AsyncGraph::Runner.new(graph))
        @runner = runner
        @executor = executor
      end

      def run(state:)
        parent = state.fetch(:req)
        request_results = {}
        run = @runner.start_run(state:, token_uid: initial_token_uid(state))

        until run.finished?
          run = @runner.advance_run(
            run: run,
            resolved_for: lambda do |token|
              # AsyncGraph хранит только ссылки на внешние await-результаты.
              # Здесь runtime подставляет уже полученные данные обратно в токен.
              token.fetch(:awaits, {}).each_with_object({}) do |(key, request_ref), resolved|
                resolved[key.to_s] = request_results.fetch(request_ref) if request_results.key?(request_ref)
              end
            end
          ) do |request|
            request_ref = build_request_ref
            # В этом месте suspended request уходит из графа в boundary runtime.
            request_results[request_ref] = @executor.call(request, parent: parent)
            request_ref
          end
        end

        final_state = run.result
        raise ValidationError, "Graph run did not produce a final state" if final_state.nil?

        final_state
      end

      private

      def initial_token_uid(state)
        request_id = Runtime::Util.text(state.dig(:req, :request_id))
        return "run-#{request_id}" if request_id

        "run-#{Runtime::Util.generate_uuid}"
      end

      def build_request_ref
        "request-#{Runtime::Util.generate_uuid}"
      end
    end
  end
end

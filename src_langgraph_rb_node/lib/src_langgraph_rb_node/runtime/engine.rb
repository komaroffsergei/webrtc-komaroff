# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    class Engine
      def initialize(io:, memory_recent_messages:, memory_summary_max_chars:, memory_context_max_chars:, registry: SrcLanggraphRbNode.built_in_registry)
        @io = io
        @memory_recent_messages = [2, memory_recent_messages.to_i].max
        @memory_summary_max_chars = [200, memory_summary_max_chars.to_i].max
        @memory_context_max_chars = [300, memory_context_max_chars.to_i].max
        @registry = registry
        @request_executor = RequestExecutor.new(io: io)
      end

      def run(req)
        user_turn_id = Runtime::Util.text(req[:turn_id]) || Runtime::Util.generate_uuid
        assistant_turn_id = Runtime::Util.generate_uuid
        req_with_turn = req.merge(turn_id: user_turn_id)
        memory = Runtime::Memory.prepare_dialog_memory(
          req: req_with_turn,
          recent_messages_limit: @memory_recent_messages,
          summary_max_chars: @memory_summary_max_chars,
          context_max_chars: @memory_context_max_chars
        )
        context_artifacts = Runtime::Util.extract_hash(memory[:context_extra][:artifact_memory])

        state = {
          req: req_with_turn,
          summary: memory[:summary],
          history: memory[:recent_turns],
          dialog_context: memory[:dialog_context],
          context_extra: memory[:context_extra],
          context_artifacts: context_artifacts,
          user_turn_id: user_turn_id,
          assistant_turn_id: assistant_turn_id,
          router_scenarios: Runtime::Router.routing_entries(@registry)
        }

        selected_scenario, routing = initial_scenario(req_with_turn, state)
        state[:selected_scenario] = selected_scenario
        state[:routing] = routing
        response = run_selected_scenario(selected_scenario, state)
        finalize_response(state.merge(response: response), response)
      end

      def choose_scenario(req, dialog_context:, excluded_scenarios: nil, context_artifacts: nil)
        Runtime::Router.choose_scenario(
          req,
          @io,
          registry: @registry,
          dialog_context: dialog_context,
          excluded_scenarios: excluded_scenarios,
          context_artifacts: context_artifacts
        )
      end

      def run_selected_scenario(scenario_id, state)
        scenario = @registry.fetch(scenario_id)
        graph_runner = GraphRunner.new(graph: scenario.graph, executor: @request_executor)
        final_state = graph_runner.run(
          state: state.merge(
            current_scenario_id: scenario.id,
            scenario_runner: method(:run_selected_scenario)
          )
        )
        response = Runtime::Util.extract_hash(final_state[:response])
        raise "Scenario '#{scenario_id}' did not produce WorkflowRunResponse" if response.empty?

        response
      end

      private

      def initial_scenario(req, state)
        active = req.dig(:runtime, :active_workflow_id).to_s.strip
        return [active, { reason: "direct_start" }] unless active.empty?

        choose_scenario(
          req,
          dialog_context: state[:dialog_context].to_s,
          context_artifacts: state[:context_artifacts]
        )
      end

      def finalize_response(state, resp)
        summary = state[:summary].to_s.strip
        history = Array(state[:history])
        context_extra = Runtime::Util.extract_hash(state[:context_extra])
        context_extra = with_artifact_memory(context_extra, Array(resp[:client_events]))
        user_turn_id = Runtime::Util.text(state[:user_turn_id]) || Runtime::Util.generate_uuid
        assistant_turn_id = Runtime::Util.text(state[:assistant_turn_id]) || Runtime::Util.generate_uuid
        assistant_text = Runtime::Memory.response_message_text(resp)

        updated_history = Runtime::Memory.append_exchange(
          recent_turns: history,
          user_turn_id: user_turn_id,
          user_text: state.dig(:req, :text).to_s,
          assistant_turn_id: assistant_turn_id,
          assistant_text: assistant_text
        )
        next_summary, next_recent = Runtime::Memory.compact_memory(
          summary: summary,
          recent_turns: updated_history,
          recent_messages_limit: @memory_recent_messages,
          summary_max_chars: @memory_summary_max_chars
        )
        next_runtime = Runtime::Util.extract_hash(resp[:next_runtime]).merge(
          context: Runtime::Memory.context_with_memory(summary: next_summary, recent_turns: next_recent, extra: context_extra)
        )
        with_runtime = resp.merge(next_runtime: next_runtime)
        with_turn_ids(with_runtime, user_turn_id: user_turn_id, assistant_turn_id: assistant_turn_id)
      end

      def with_turn_ids(resp, user_turn_id:, assistant_turn_id:)
        handler = Runtime::Util.extract_hash(resp[:client_handler])
        command = handler[:command].to_s
        if command.empty? && resp[:status] == "FAILED"
          message = Runtime::Memory.response_message_text(resp)
          handler = { command: "SHOW_ERROR_MESSAGE", payload: { message: message.empty? ? "Request failed." : message } }
        elsif command.empty?
          return resp
        end

        payload = Runtime::Util.extract_hash(handler[:payload])
        payload[:user_turn_id] ||= user_turn_id
        payload[:assistant_turn_id] ||= assistant_turn_id
        resp.merge(client_handler: handler.merge(payload: payload))
      end

      def with_artifact_memory(context_extra, client_events)
        out = Runtime::Util.extract_hash(context_extra)
        artifact = Runtime::Util.extract_hash(out[:artifact_memory])

        client_events.each do |event|
          ev = Runtime::Util.extract_hash(event)
          command = ev[:command].to_s.upcase
          data = Runtime::Util.extract_hash(Runtime::Util.extract_hash(ev[:payload])[:data])
          case command
          when "SET_AIRPORTS"
            airports = Array(data[:airports]).first(10).filter_map do |item|
              next unless item.is_a?(Hash)

              payload = Runtime::Util.extract_hash(item)
              {
                id: payload[:id],
                code: payload[:code],
                name: payload[:name],
                status: payload[:status],
                lat: payload[:lat],
                lon: payload[:lon]
              }
            end
            artifact[:last_airports] = airports unless airports.empty?
          when "SET_POSITION"
            position = Runtime::Util.extract_hash(data[:current_position])
            artifact[:last_position] = {
              city: position[:city],
              lat: position[:lat],
              lon: position[:lon]
            } unless position.empty?
          when "BUILD_ROUTE"
            route = Runtime::Util.extract_hash(data[:route])
            route_data = route[:data].is_a?(Hash) ? Runtime::Util.extract_hash(route[:data]) : route
            geometry = Array(route_data[:geometry]).first(1000).filter_map do |point|
              next unless point.is_a?(Array) || point.is_a?(Struct)
              next unless point.length == 2 && point[0].is_a?(Numeric) && point[1].is_a?(Numeric)

              [point[0].to_f, point[1].to_f]
            end
            artifact[:last_route] = {
              distance_km: route_data[:distance_km],
              duration_min: route_data[:duration_min],
              geometry: geometry,
              from: route_data[:from].is_a?(Hash) ? Runtime::Util.extract_hash(route_data[:from]) : nil,
              to: route_data[:to].is_a?(Hash) ? Runtime::Util.extract_hash(route_data[:to]) : nil
            } unless route_data.empty?
          end
        end

        out[:artifact_memory] = artifact unless artifact.empty?
        out
      end
    end
  end
end

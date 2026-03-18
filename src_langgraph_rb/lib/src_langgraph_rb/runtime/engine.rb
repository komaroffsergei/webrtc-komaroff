# frozen_string_literal: true

require "set"

module SrcLanggraphRb
  module Runtime
    class Engine
      def initialize(io:, memory_recent_messages:, memory_summary_max_chars:, memory_context_max_chars:)
        @io = io
        @memory_recent_messages = [2, memory_recent_messages.to_i].max
        @memory_summary_max_chars = [200, memory_summary_max_chars.to_i].max
        @memory_context_max_chars = [300, memory_context_max_chars.to_i].max
        @catalog = SrcLanggraphRb.built_in_catalog
        @graphs = build_graphs
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

        state = {
          req: req_with_turn,
          summary: memory[:summary],
          history: memory[:recent_turns],
          dialog_context: memory[:dialog_context],
          context_extra: memory[:context_extra],
          user_turn_id: user_turn_id,
          assistant_turn_id: assistant_turn_id
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
          catalog: @catalog,
          dialog_context: dialog_context,
          excluded_scenarios: excluded_scenarios,
          context_artifacts: context_artifacts
        )
      end

      def run_selected_scenario(scenario_id, state)
        graph = @graphs.fetch(scenario_id) do
          raise SrcLanggraphRb::RegistryError, "Scenario '#{scenario_id}' is not registered in Ruby runtime"
        end

        final_state = graph.invoke(state, context: { engine: self, io: @io })
        response = Runtime::Util.extract_hash(final_state[:response])
        raise "Scenario '#{scenario_id}' did not produce WorkflowRunResponse" if response.empty?

        response
      end

      private

      def initial_scenario(req, state)
        pending = Runtime::Util.extract_hash(req.dig(:runtime, :pending))
        active = req.dig(:runtime, :active_workflow_id).to_s.strip
        return [active, {}] if !pending.empty? && resumable_scenario?(active)

        context_artifacts = Runtime::Util.extract_hash(Runtime::Util.extract_hash(state[:context_extra])[:artifact_memory])
        choose_scenario(req, dialog_context: state[:dialog_context].to_s, context_artifacts: context_artifacts)
      end

      def build_graphs
        @catalog.all.each_with_object({}) do |scenario, out|
          plan = @catalog.to_builder_plan(scenario.id)
          graph = plan.build_graph(
            node_resolver: ->(instruction) { node_callable(scenario, instruction) },
            router_resolver: ->(instruction) { router_callable(instruction) }
          )
          graph.compile!
          out[scenario.id] = graph
        end
      end

      def node_callable(scenario, instruction)
        kind = instruction.fetch(:kind).to_s
        config = Runtime::Util.deep_symbolize(instruction.fetch(:config, {}))
        lambda do |state, context|
          case kind
          when "compute"
            Runtime::ComputeOps.call(
              op: config.fetch(:op),
              state: state,
              io: context.fetch(:io),
              engine: context.fetch(:engine),
              scenario_id: scenario.id,
              config: config
            )
          when "tool_call"
            generic_tool_call(state, context.fetch(:io), config)
          when "final_response"
            { response: Runtime::Responses.done_response(state.fetch(:req), state[:response_message].to_s, client_events: state[:client_events]) }
          when "state_response"
            ensure_response!(state)
            {}
          when "done_response"
            message = state[config.fetch(:message_source, :response_message)].to_s
            { response: Runtime::Responses.done_response(state.fetch(:req), message, client_events: state[:client_events]) }
          when "failed_response"
            {
              response: Runtime::Responses.failed_response(
                state.fetch(:req),
                code: state[:error_code].to_s.empty? ? "workflow_failed" : state[:error_code].to_s,
                message: state[:error_message].to_s.empty? ? "Workflow failed." : state[:error_message].to_s,
                runtime: state[:error_runtime],
                client_handler: state[:error_client_handler]
              )
            }
          when "partial_response"
            {
              response: Runtime::Responses.partial_response(
                state.fetch(:req),
                state[:response_prompt].to_s,
                active_workflow_id: config[:active_workflow_id].to_s.empty? ? scenario.id : config[:active_workflow_id].to_s,
                pending: Runtime::Util.extract_hash(state[:pending_state])
              )
            }
          else
            raise SrcLanggraphRb::ValidationError, "Unsupported runtime node kind '#{kind}'"
          end
        end
      end

      def generic_tool_call(state, io, config)
        args_source = config[:args_source].to_s
        args = args_source == "empty_args" ? {} : Runtime::Util.extract_hash(state[args_source.to_sym])
        resp = io.call_tool(parent: state.fetch(:req), tool_name: config.fetch(:tool_name).to_s, args: args)
        out = {
          last_tool_response: resp,
          last_tool_ok: resp[:ok],
          error_code: nil,
          error_message: nil,
          error_client_handler: nil
        }
        result_key = config[:result_key]
        out[result_key.to_sym] = resp if result_key
        unless resp[:ok]
          code = Runtime::Util.extract_hash(resp[:error])[:code].to_s
          code = "tool_failed" if code.empty?
          message = config[:failure_message].to_s.strip
          message = Runtime::Util.extract_hash(resp[:error])[:message].to_s.strip if message.empty?
          message = "Tool request failed." if message.empty?
          out[:error_code] = code
          out[:error_message] = message
        end
        out
      end

      def ensure_response!(state)
        raise "runtime state response is missing" if Runtime::Util.extract_hash(state[:response]).empty?
      end

      def resumable_scenario?(scenario_id)
        scenario = @catalog.all.find { |item| item.id.to_s == scenario_id.to_s }
        return false unless scenario

        flags = Runtime::Util.extract_hash(scenario.metadata.runtime_flags)
        !flags[:pending_key].to_s.strip.empty?
      end

      def router_callable(instruction)
        router = instruction.fetch(:router).to_s
        lambda do |state, _context|
          return state[:last_tool_ok] ? "ok" : "failed" if router == "tool_status"

          state[router.to_sym]
        end
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
        with_turn_ids(with_runtime, user_turn_id:, assistant_turn_id:)
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

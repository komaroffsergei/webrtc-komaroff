# frozen_string_literal: true

module SrcLanggraphRb
  module DSL
    class GraphBuilder < FragmentBuilder
      def initialize(fragment_lookup:, tool_profiles:, scenario_id:)
        super("__graph__")
        @fragment_lookup = fragment_lookup
        @tool_profiles = normalize_profiles(tool_profiles)
        @scenario_id = scenario_id.to_s
        @entry_point = nil
        @imports = []
        @required_tools = []
        @pending_key = nil
      end

      attr_reader :pending_key

      def required_tools
        @required_tools.dup.freeze
      end

      def pending_enabled?
        !@pending_key.nil?
      end

      def entry_point(id)
        @entry_point = Support::Identifiers.normalize_id(id)
      end

      def use(name, as:)
        fragment = @fragment_lookup.call(name)
        Support::FragmentImporter.import!(builder: self, fragment:, as:)
      end

      def use_default_tails
        use :assistant_reply_tail, as: :final
        use :state_response_tail, as: :terminal
      end

      def ref(namespace, node_name)
        Support::Identifiers.namespaced_id(namespace, node_name)
      end

      def final(node_name = :respond)
        ref(:final, node_name)
      end

      def terminal(node_name = :respond)
        ref(:terminal, node_name)
      end

      def status_of(node_id)
        :"#{normalize_node_id(node_id)}_status"
      end

      def response_of(node_id)
        :"#{normalize_node_id(node_id)}_response"
      end
      alias result_of response_of

      def params_of(node_id)
        :"#{normalize_node_id(node_id)}_params"
      end

      def prompt_of(node_id)
        :"#{normalize_node_id(node_id)}_prompt"
      end

      def pending_of(node_id)
        :"#{normalize_node_id(node_id)}_pending"
      end

      def message_of(node_id)
        :"#{normalize_node_id(node_id)}_message"
      end

      def register_import(name, alias_name)
        @imports << Schema::FragmentImport.new(name.to_s, Support::Identifiers.normalize_id(alias_name))
      end

      def tool(id, tool_name:, args_source: :empty_args, result_key: nil, failure_message: nil, **config)
        tool_name_text = normalize_tool_name(tool_name)
        track_tool(tool_name_text)
        node(
          id,
          kind: :tool_call,
          tool_name: tool_name_text,
          args_source: args_source,
          result_key: result_key || response_of(id),
          failure_message: failure_message,
          **config
        )
      end

      def resolve_context_refs(id, status_key: nil, clarify_message_key: nil, **config)
        node(
          id,
          kind: :compute,
          op: :resolve_context_references,
          status_key: status_key || status_of(id),
          clarify_message_key: clarify_message_key || message_of(id),
          **config
        )
      end

      def free_speech_response(id, task:, scenario_context:, fallback_message:, primary_constraints: nil, retry_constraints: nil, retry_task_suffix: nil, status_key: nil, **config)
        node(
          id,
          kind: :compute,
          op: :compose_free_speech_response,
          task: task,
          scenario_context: scenario_context,
          fallback_message: fallback_message,
          retry_task_suffix: retry_task_suffix,
          primary_constraints: primary_constraints,
          retry_constraints: retry_constraints,
          status_key: status_key || status_of(id),
          **config
        )
      end

      def pending_tool_params(id, profile:, ready_if_any_present:, pending_missing:, followup_pattern:, reroute: true, ask_input_default: nil, status_key: nil, merged_key: nil, prompt_key: nil, pending_key: nil, pending_scenario_id: nil, excluded_scenarios: nil, **config)
        profile_config = tool_profile!(profile)
        tool_name_text = fetch_profile_value(profile_config, :tool_name)
        track_tool(tool_name_text)
        @pending_key ||= profile.to_sym

        node(
          id,
          kind: :compute,
          op: :collect_tool_params_with_pending,
          task: fetch_profile_value(profile_config, :params_task),
          tool_name: tool_name_text,
          tool_schema: fetch_profile_value(profile_config, :tool_schema, default: {}),
          ask_input_default: ask_input_default || profile_config[:ask_input_default],
          ready_if_any_present: ready_if_any_present,
          pending_missing: pending_missing,
          pending_scenario_id: pending_scenario_id || @scenario_id,
          followup_pattern: followup_pattern,
          status_key: status_key || status_of(id),
          merged_key: merged_key || params_of(id),
          prompt_key: prompt_key || prompt_of(id),
          pending_key: pending_key || pending_of(id),
          excluded_scenarios: reroute ? (excluded_scenarios || [@scenario_id]) : [],
          **config
        )
      end

      def tool_lookup_response(id, profile:, args_source:, status_key: nil, not_found_code: "not_found", not_found_message: nil, failure_message: nil, fallback_formatter: nil, **config)
        profile_config = tool_profile!(profile)
        tool_name_text = fetch_profile_value(profile_config, :tool_name)
        track_tool(tool_name_text)

        node(
          id,
          kind: :compute,
          op: :tool_lookup_with_llm_response,
          tool_name: tool_name_text,
          args_source: args_source,
          task: fetch_profile_value(profile_config, :final_task),
          scenario_context: profile_config[:scenario_context].to_s,
          status_key: status_key || status_of(id),
          not_found_code: not_found_code,
          not_found_message: not_found_message || profile_config[:not_found_message],
          failure_message: failure_message || profile_config[:failure_message],
          fallback_formatter: fallback_formatter || profile_config[:fallback_formatter],
          **config
        )
      end

      def airport_search_params(id, profile:, position_tool_name:, position_source:, position_key: :current_position, tool_results_key: :tool_results, args_key: :search_args, default_city: nil, default_radius_km: nil, **config)
        profile_config = tool_profile!(profile)
        search_tool_name = fetch_profile_value(profile_config, :tool_name)
        track_tool(position_tool_name)
        track_tool(search_tool_name)

        node(
          id,
          kind: :compute,
          op: :prepare_airport_search,
          task: fetch_profile_value(profile_config, :params_task),
          position_tool_name: normalize_tool_name(position_tool_name),
          search_tool_name: search_tool_name,
          tool_schema: fetch_profile_value(profile_config, :tool_schema, default: {}),
          default_city: default_city || profile_config[:default_city],
          default_radius_km: default_radius_km || profile_config[:default_radius_km],
          position_source: position_source,
          position_key: position_key,
          tool_results_key: tool_results_key,
          args_key: args_key,
          **config
        )
      end

      def airport_route_params(id, profile:, search_tool_name:, search_response_key:, tool_results_key: :tool_results, current_position_key: :current_position, route_args_key: :route_args, status_key: nil, failure_message: nil, failure_code: nil, **config)
        profile_config = tool_profile!(profile)
        route_tool_name = fetch_profile_value(profile_config, :tool_name)
        track_tool(search_tool_name)
        track_tool(route_tool_name)

        node(
          id,
          kind: :compute,
          op: :prepare_airport_route,
          task: fetch_profile_value(profile_config, :params_task),
          search_tool_name: normalize_tool_name(search_tool_name),
          route_tool_name: route_tool_name,
          tool_schema: fetch_profile_value(profile_config, :tool_schema, default: {}),
          search_response_key: search_response_key,
          tool_results_key: tool_results_key,
          current_position_key: current_position_key,
          route_args_key: route_args_key,
          status_key: status_key || status_of(id),
          failure_message: failure_message || profile_config[:failure_message],
          failure_code: failure_code,
          **config
        )
      end

      def route_response(id, profile:, args_source:, search_response_key:, tool_results_key: :tool_results, current_position_key: :current_position, status_key: nil, failure_message: nil, fallback_message: nil, **config)
        profile_config = tool_profile!(profile)
        tool_name_text = fetch_profile_value(profile_config, :tool_name)
        track_tool(tool_name_text)

        node(
          id,
          kind: :compute,
          op: :build_route_with_response,
          tool_name: tool_name_text,
          args_source: args_source,
          search_response_key: search_response_key,
          tool_results_key: tool_results_key,
          current_position_key: current_position_key,
          task: fetch_profile_value(profile_config, :final_task),
          scenario_context: profile_config[:scenario_context].to_s,
          status_key: status_key || status_of(id),
          failure_message: failure_message || profile_config[:failure_message],
          fallback_message: fallback_message || profile_config[:fallback_message],
          **config
        )
      end

      def ask_user_input(id, from: nil, prompt_source: nil, pending_source: nil, active_workflow_id: nil, **config)
        node(
          id,
          kind: :partial_response,
          prompt_source: prompt_source || (from ? prompt_of(from) : :response_prompt),
          pending_source: pending_source || (from ? pending_of(from) : :pending_state),
          active_workflow_id: active_workflow_id,
          **config
        )
      end

      def done(id, message_source: :response_message, **config)
        node(id, kind: :done_response, message_source: message_source, **config)
      end

      def failed(id, code_source: :error_code, message_source: :error_message, runtime_source: :error_runtime, client_handler_source: :error_client_handler, **config)
        node(
          id,
          kind: :failed_response,
          code_source: code_source,
          message_source: message_source,
          runtime_source: runtime_source,
          client_handler_source: client_handler_source,
          **config
        )
      end

      def reroute_scenario(id, scenario_source: :reroute_scenario_id, **config)
        node(id, kind: :compute, op: :reroute_selected_scenario, scenario_source: scenario_source, **config)
      end

      def route_status(from, path_map)
        conditional_edge(from, status_of(from), path_map)
      end

      def route_tool_status(from, ok:, failed:)
        conditional_edge(from, :tool_status, { "ok" => ok, "failed" => failed })
      end

      def finish_with_state(*nodes)
        nodes.flatten.each do |node_name|
          edge(node_name, terminal)
        end
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

      private

      def normalize_profiles(tool_profiles)
        return {} unless tool_profiles.is_a?(Hash)

        tool_profiles.each_with_object({}) do |(name, config), out|
          out[name.to_s] = Support::Normalization.normalize_hash(config)
        end
      end

      def tool_profile!(name)
        @tool_profiles.fetch(name.to_s) do
          raise ValidationError, "Tool profile '#{name}' is not registered in scenario '#{@scenario_id}'"
        end
      end

      def fetch_profile_value(profile_config, key, default: nil)
        value = profile_config[key.to_sym]
        value = default if value.nil?
        return value unless value.nil?

        raise ValidationError, "Tool profile value '#{key}' is required in scenario '#{@scenario_id}'"
      end

      def track_tool(tool_name)
        text = normalize_tool_name(tool_name)
        @required_tools << text unless @required_tools.include?(text)
      end

      def normalize_tool_name(tool_name)
        text = tool_name.to_s.strip
        raise ValidationError, "Tool name must be provided" if text.empty?

        text
      end

      def normalize_node_id(node_id)
        Support::Identifiers.normalize_id(node_id)
      end
    end
  end
end

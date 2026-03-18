# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module ComputeOps
      module_function

      SINGULAR_REF_RE = /\b(он|она|оно|его|ее|её|нему|ней|нем|этот|эта|это|данный|данная)\b/i
      PLURAL_REF_RE = /\b(они|их|ими|эти|этих|этим)\b/i
      FACT_QUERY_RE = /\b(когда|в каком году|какого года|какой год|какие годы|кем|кто|где|почему|что известно|история|год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?|основан(?:а|о|ы)?|основание|построен(?:а|о|ы)?|постройк(?:а|и)|строительств(?:о|а)|открыт(?:а|о|ы)?|создан(?:а|о|ы)?)\b/i
      YEAR_QUERY_RE = /\b(в каком году|какого года|какой год|какие годы|год(?:а|у|ом)?(?:\s+(?:основания|постройки|создания|строительства))?)\b/i
      YEAR_VALUE_RE = /\b(1[6-9]\d{2}|20\d{2}|21\d{2})\b/
      CONTEXT_ONLY_REFUSAL_HINTS = [
        "в текущих данных нет",
        "в текущем контексте нет",
        "в контексте нет этой информации",
        "в контексте нет данных",
        "в диалоге нет этой информации",
        "в текущем диалоге нет",
        "нет подтвержденной информации",
        "не могу указать",
        "к сожалению, я не уверен",
        "я не уверен, кто",
        "могу помочь с тем, что известно в текущем диалоге",
        "данных о годе"
      ].freeze
      KNOWLEDGE_RETRY_TASK_SUFFIX = "Если вопрос пользователя требует фактов, не ограничивайся только полями из context_artifacts.\n" \
                                    "Используй общие знания модели вместе с контекстом диалога.\n" \
                                    "Считай context_artifacts подсказками, а не ограничением знаний.\n" \
                                    "Для вопросов про даты/историю/авторство используй знания модели, даже если в context_artifacts нет этих данных.\n" \
                                    "Не отвечай шаблоном о нехватке данных, если факт можно дать из общих знаний.\n" \
                                    "Если уверенность низкая, прямо укажи это в ответе."

      def call(op:, state:, io:, engine:, scenario_id:, config:)
        case op.to_s
        when "resolve_context_references"
          resolve_context_references(state, config)
        when "compose_free_speech_response"
          compose_free_speech_response(state, io:, config:)
        when "collect_tool_params_with_pending"
          collect_tool_params_with_pending(state, io:, engine:, scenario_id:, config:)
        when "reroute_selected_scenario"
          reroute_selected_scenario(state, engine:, config:)
        when "tool_lookup_with_llm_response"
          tool_lookup_with_llm_response(state, io:, config:)
        when "prepare_airport_search"
          prepare_airport_search(state, io:, config:)
        when "prepare_airport_route"
          prepare_airport_route(state, io:, config:)
        when "build_route_with_response"
          build_route_with_response(state, io:, config:)
        else
          raise SrcLanggraphRb::ValidationError, "Unsupported compute op '#{op}'"
        end
      end

      def resolve_context_references(state, config)
        extra = Runtime::Util.extract_hash(state[:context_extra])
        entities = extract_entities_from_artifacts(extra)
        resolved_mode, resolved_entities, resolved_hint = resolve_entity_reference(
          state.dig(:req, :text).to_s,
          entities,
          dialog_context: state[:dialog_context].to_s
        )

        status_key = fetch_key(config, :status_key, :free_speech_entry)
        clarify_key = fetch_key(config, :clarify_message_key, :clarify_message)
        out = {
          resolved_mode: resolved_mode,
          resolved_entities: resolved_entities,
          resolved_hint: resolved_hint,
          context_artifacts: Runtime::Util.extract_hash(extra[:artifact_memory]),
          status_key => resolved_mode == "clarify" ? "clarify" : "continue"
        }
        out[clarify_key] = clarify_entity_message(resolved_entities) if resolved_mode == "clarify"
        out
      end

      def compose_free_speech_response(state, io:, config:)
        req = state.fetch(:req)
        status_key = fetch_key(config, :status_key, :free_speech_result)
        task = config.fetch(:task).to_s
        scenario_context = config[:scenario_context].to_s
        fallback_message = config[:fallback_message].to_s.strip
        fallback_message = "Сервис ответов временно недоступен. Попробуйте повторить запрос." if fallback_message.empty?

        primary_input = {
          task: task,
          user_message: req[:text],
          tool_results: [],
          scenario_context: scenario_context,
          dialog_context: state[:dialog_context].to_s,
          context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts]),
          resolved_reference_mode: %w[single multi].include?(state[:resolved_mode]) ? state[:resolved_mode] : "none",
          resolved_entities: Array(state[:resolved_entities]).first(5),
          resolved_hint: state[:resolved_hint].to_s,
          free_speech_pass: "primary"
        }
        primary_resp = io.call_llm(
          parent: req,
          mode: "final_response",
          input_data: primary_input,
          constraints: Runtime::Util.extract_hash(config[:primary_constraints]).empty? ? { temperature: 0.4 } : Runtime::Util.extract_hash(config[:primary_constraints])
        )
        unless primary_resp[:ok]
          return {
            response: Runtime::Responses.done_response(req, fallback_message),
            status_key => "terminal"
          }
        end

        primary_text = extract_llm_text(primary_resp).to_s
        unless needs_knowledge_retry(
          user_text: req[:text].to_s,
          response_text: primary_text,
          resolved_mode: state[:resolved_mode].to_s,
          resolved_entities: Array(state[:resolved_entities])
        )
          return {
            response_message: primary_text.empty? ? "Чем могу помочь?" : primary_text,
            status_key => "done"
          }
        end

        secondary_input = primary_input.merge(
          task: [task, config[:retry_task_suffix].to_s.strip, KNOWLEDGE_RETRY_TASK_SUFFIX].reject(&:empty?).join("\n"),
          dialog_context: short_dialog_context(state[:dialog_context].to_s),
          context_artifacts: retry_context_artifacts(
            context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts]),
            resolved_entities: Array(state[:resolved_entities])
          ),
          free_speech_pass: "knowledge_retry",
          retry_reason: retry_reason(
            user_text: req[:text].to_s,
            response_text: primary_text,
            resolved_mode: state[:resolved_mode].to_s,
            resolved_entities: Array(state[:resolved_entities])
          )
        )
        secondary_resp = io.call_llm(
          parent: req,
          mode: "final_response",
          input_data: secondary_input,
          constraints: Runtime::Util.extract_hash(config[:retry_constraints]).empty? ? { temperature: 0.3 } : Runtime::Util.extract_hash(config[:retry_constraints])
        )
        secondary_text = extract_llm_text(secondary_resp).to_s

        primary_score = response_quality_score(
          user_text: req[:text].to_s,
          response_text: primary_text,
          resolved_mode: state[:resolved_mode].to_s,
          resolved_entities: Array(state[:resolved_entities])
        )
        secondary_score = response_quality_score(
          user_text: req[:text].to_s,
          response_text: secondary_text,
          resolved_mode: state[:resolved_mode].to_s,
          resolved_entities: Array(state[:resolved_entities])
        )
        best_text = secondary_score >= primary_score ? secondary_text : primary_text
        {
          response_message: [best_text, primary_text, "Чем могу помочь?"].find { |item| !item.to_s.empty? },
          status_key => "done"
        }
      end

      def collect_tool_params_with_pending(state, io:, engine:, scenario_id:, config:)
        req = state.fetch(:req)
        pending = Runtime::Util.extract_hash(req.dig(:runtime, :pending))
        had_pending = !pending.empty?
        prev = pending[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(pending[:extracted]) : {}

        params_resp = io.call_llm(
          parent: req,
          mode: "tool_params",
          input_data: {
            task: config.fetch(:task).to_s,
            user_message: req[:text],
            tool_name: config.fetch(:tool_name).to_s,
            tool_schema: Runtime::Util.extract_hash(config[:tool_schema]),
            dialog_context: state[:dialog_context].to_s
          },
          constraints: Runtime::Util.extract_hash(config[:constraints]).empty? ? { temperature: 0 } : Runtime::Util.extract_hash(config[:constraints])
        )
        parsed = normalize_tool_params(params_resp)
        merged = merge_non_empty_params(prev, parsed[:extracted])
        status_key = fetch_key(config, :status_key, :tool_param_status)
        merged_key = fetch_key(config, :merged_key, :merged_params)
        prompt_key = fetch_key(config, :prompt_key, :response_prompt)
        pending_key = fetch_key(config, :pending_key, :pending_state)

        if ready_with_any_field?(merged, Array(config[:ready_if_any_present]))
          return { merged_key => merged, status_key => "ready" }
        end

        prompt = parsed[:prompt].to_s.strip
        prompt = config[:ask_input_default].to_s.strip if prompt.empty?
        pending_state = {
          type: config[:pending_type].to_s.empty? ? "tool_params" : config[:pending_type].to_s,
          scenario_id: config[:pending_scenario_id].to_s.empty? ? scenario_id : config[:pending_scenario_id].to_s,
          tool_name: config.fetch(:tool_name).to_s,
          extracted: merged,
          missing: Array(config[:pending_missing]).map(&:to_s),
          prompt: prompt
        }

        if had_pending
          followup_re = regexp_from_config(config[:followup_pattern])
          if followup_re&.match?(req[:text].to_s)
            return {
              merged_key => merged,
              prompt_key => prompt,
              pending_key => pending_state,
              status_key => "missing"
            }
          end

          _summary, _recent, context_extra = Runtime::Memory.memory_from_context(req.dig(:runtime, :context))
          context_artifacts = Runtime::Util.extract_hash(context_extra[:artifact_memory])
          reroute_scenario_id, _routing = engine.choose_scenario(
            req,
            dialog_context: state[:dialog_context].to_s,
            excluded_scenarios: begin
              values = Array(config[:excluded_scenarios]).map(&:to_s).reject(&:empty?)
              values.empty? ? [scenario_id] : values
            end,
            context_artifacts: context_artifacts
          )
          return { reroute_scenario_id: reroute_scenario_id, status_key => "reroute" }
        end

        {
          merged_key => merged,
          prompt_key => prompt,
          pending_key => pending_state,
          status_key => "missing"
        }
      end

      def reroute_selected_scenario(state, engine:, config:)
        scenario_source = fetch_key(config, :scenario_source, :reroute_scenario_id)
        scenario_id = state[scenario_source].to_s
        response = engine.run_selected_scenario(scenario_id, state)
        { response: response }
      end

      def tool_lookup_with_llm_response(state, io:, config:)
        req = state.fetch(:req)
        args = Runtime::Util.extract_hash(state[fetch_key(config, :args_source, :merged_params)])
        args = args.each_with_object({}) do |(key, value), out|
          next if value.nil?
          next if value.is_a?(String) && value.strip.empty?

          out[key] = value.is_a?(String) ? value.strip : value
        end

        tool_name = config.fetch(:tool_name).to_s
        status_key = fetch_key(config, :status_key, :tool_result_status)
        tool_resp = io.call_tool(parent: req, tool_name: tool_name, args: args)
        unless tool_resp[:ok]
          code = Runtime::Util.extract_hash(tool_resp[:error])[:code].to_s
          code = "tool_failed" if code.empty?
          if code == (config[:not_found_code].to_s.empty? ? "not_found" : config[:not_found_code].to_s)
            return {
              response_message: config[:not_found_message].to_s.empty? ? "Результат не найден." : config[:not_found_message].to_s,
              status_key => "not_found"
            }
          end

          failure_message = config[:failure_message].to_s.strip
          failure_message = "Запрос к инструменту завершился ошибкой." if failure_message.empty?
          return {
            error_code: code,
            error_message: failure_message,
            error_client_handler: {
              command: "SHOW_ERROR_MESSAGE",
              payload: { message: failure_message, code: code }
            },
            status_key => "failed"
          }
        end

        final_resp = io.call_llm(
          parent: req,
          mode: "final_response",
          input_data: {
            task: config.fetch(:task).to_s,
            user_message: req[:text],
            tool_results: [{ tool_name: tool_name, result: tool_resp[:data] }],
            scenario_context: config[:scenario_context].to_s,
            dialog_context: state[:dialog_context].to_s
          },
          constraints: Runtime::Util.extract_hash(config[:constraints]).empty? ? { temperature: 0.1 } : Runtime::Util.extract_hash(config[:constraints])
        )
        message = extract_llm_text(final_resp)
        message ||= fallback_tool_message(config[:fallback_formatter], tool_resp[:data])
        message ||= "Готово."
        {
          response_message: message,
          status_key => "done"
        }
      end

      def prepare_airport_search(state, io:, config:)
        req = state.fetch(:req)
        position_source = fetch_key(config, :position_source, :position_response)
        pos_resp = Runtime::Util.extract_hash(state[position_source])
        pos_data = extract_nested_data(pos_resp[:data] || pos_resp) || {}
        position_tool_name = config.fetch(:position_tool_name).to_s
        search_tool_name = config.fetch(:search_tool_name).to_s
        tool_results = [{ tool_name: position_tool_name, result: pos_resp[:data] || pos_resp }]
        search_params_resp = io.call_llm(
          parent: req,
          mode: "tool_params",
          input_data: {
            task: config.fetch(:task).to_s,
            user_message: req[:text],
            tool_name: search_tool_name,
            tool_schema: Runtime::Util.extract_hash(config[:tool_schema]),
            tool_results: tool_results,
            dialog_context: state[:dialog_context].to_s
          },
          constraints: Runtime::Util.extract_hash(config[:constraints]).empty? ? { temperature: 0 } : Runtime::Util.extract_hash(config[:constraints])
        )
        search_params = normalize_tool_params(search_params_resp)[:extracted]
        city = search_params[:city].to_s.strip
        radius_km = Runtime::Util.float(search_params[:radius_km])
        city = pos_data[:city].to_s.strip if city.empty?
        city = config[:default_city].to_s.strip if city.empty?
        default_radius = Runtime::Util.float(config[:default_radius_km], default: 50.0) || 50.0

        {
          fetch_key(config, :position_key, :current_position) => pos_data,
          fetch_key(config, :tool_results_key, :tool_results) => tool_results,
          fetch_key(config, :args_key, :search_args) => { city: city, radius_km: radius_km || default_radius }
        }
      end

      def prepare_airport_route(state, io:, config:)
        req = state.fetch(:req)
        search_response_key = fetch_key(config, :search_response_key, :search_response)
        tool_results_key = fetch_key(config, :tool_results_key, :tool_results)
        current_position_key = fetch_key(config, :current_position_key, :current_position)
        route_args_key = fetch_key(config, :route_args_key, :route_args)
        status_key = fetch_key(config, :status_key, :route_args_status)
        search_tool_name = config.fetch(:search_tool_name).to_s
        route_tool_name = config.fetch(:route_tool_name).to_s

        search_resp = Runtime::Util.extract_hash(state[search_response_key])
        tool_results = Array(state[tool_results_key]) + [{ tool_name: search_tool_name, result: search_resp[:data] || search_resp }]
        route_params_resp = io.call_llm(
          parent: req,
          mode: "tool_params",
          input_data: {
            task: config.fetch(:task).to_s,
            user_message: req[:text],
            tool_name: route_tool_name,
            tool_schema: Runtime::Util.extract_hash(config[:tool_schema]),
            tool_results: tool_results,
            dialog_context: state[:dialog_context].to_s
          },
          constraints: Runtime::Util.extract_hash(config[:constraints]).empty? ? { temperature: 0 } : Runtime::Util.extract_hash(config[:constraints])
        )
        route_params = normalize_tool_params(route_params_resp)[:extracted]
        airports_data = extract_nested_data(search_resp[:data] || search_resp) || {}
        route_args = normalize_route_args(route_params, Runtime::Util.extract_hash(state[current_position_key]), airports_data)
        return { route_args_key => route_args, tool_results_key => tool_results, status_key => "ready" } if route_args

        {
          error_code: config[:failure_code].to_s.empty? ? "route_params_missing" : config[:failure_code].to_s,
          error_message: config[:failure_message].to_s.empty? ? "Не удалось собрать координаты для маршрута." : config[:failure_message].to_s,
          status_key => "failed"
        }
      end

      def build_route_with_response(state, io:, config:)
        req = state.fetch(:req)
        args = Runtime::Util.extract_hash(state[fetch_key(config, :args_source, :route_args)])
        status_key = fetch_key(config, :status_key, :route_result_status)
        route_tool_name = config.fetch(:tool_name).to_s

        route_resp = io.call_tool(parent: req, tool_name: route_tool_name, args: args)
        unless route_resp[:ok]
          code = Runtime::Util.extract_hash(route_resp[:error])[:code].to_s
          code = "tool_failed" if code.empty?
          return {
            error_code: code,
            error_message: config[:failure_message].to_s.empty? ? "Не удалось построить маршрут." : config[:failure_message].to_s,
            status_key => "failed"
          }
        end

        search_resp = Runtime::Util.extract_hash(state[fetch_key(config, :search_response_key, :search_response)])
        tool_results_key = fetch_key(config, :tool_results_key, :tool_results)
        tool_results = Array(state[tool_results_key]) + [{ tool_name: route_tool_name, result: route_resp[:data] }]
        final_resp = io.call_llm(
          parent: req,
          mode: "final_response",
          input_data: {
            task: config.fetch(:task).to_s,
            user_message: req[:text],
            tool_results: tool_results,
            scenario_context: config[:scenario_context].to_s,
            dialog_context: state[:dialog_context].to_s
          },
          constraints: Runtime::Util.extract_hash(config[:constraints]).empty? ? { temperature: 0.1 } : Runtime::Util.extract_hash(config[:constraints])
        )
        message = extract_llm_text(final_resp) || config[:fallback_message].to_s.strip
        message = "Маршрут построен." if message.to_s.empty?

        airports_data = extract_nested_data(search_resp[:data] || search_resp) || {}
        route_data = extract_nested_data(route_resp[:data]) || {}
        {
          response_message: message,
          client_events: [
            { command: "SET_POSITION", payload: { data: { current_position: Runtime::Util.extract_hash(state[fetch_key(config, :current_position_key, :current_position)]) } } },
            { command: "SET_AIRPORTS", payload: { data: { airports: airports_data[:airports] || [] } } },
            { command: "BUILD_ROUTE", payload: { data: { route: route_data } } }
          ],
          status_key => "done"
        }
      end

      def fetch_key(config, name, default)
        (config[name] || default).to_sym
      end
      private_class_method :fetch_key

      def regexp_from_config(value)
        return value if value.is_a?(Regexp)
        return nil unless value.is_a?(String) && !value.strip.empty?

        Regexp.new(value, Regexp::IGNORECASE)
      end
      private_class_method :regexp_from_config

      def ready_with_any_field?(payload, fields)
        Array(fields).map(&:to_sym).any? do |key|
          value = payload[key]
          value.is_a?(String) ? !value.strip.empty? : !value.nil?
        end
      end
      private_class_method :ready_with_any_field?

      def extract_llm_text(resp)
        data = Runtime::Util.extract_hash(resp[:data])
        value = data[:response_text]
        return nil unless value.is_a?(String) && !value.strip.empty?

        value.strip
      end
      private_class_method :extract_llm_text

      def normalize_tool_params(resp)
        data = resp[:ok] ? Runtime::Util.extract_hash(resp[:data]) : {}
        extracted = data[:extracted].is_a?(Hash) ? Runtime::Util.extract_hash(data[:extracted]) : {}
        missing = Array(data[:missing]).map(&:to_s)
        prompt = data[:prompt]
        prompt = prompt.to_s if !prompt.nil? && !prompt.is_a?(String)
        { extracted: extracted, missing: missing, prompt: prompt }
      end
      private_class_method :normalize_tool_params

      def merge_non_empty_params(base, new_values)
        merged = Runtime::Util.extract_hash(base)
        Runtime::Util.extract_hash(new_values).each do |key, value|
          next if value.nil?
          next if value.is_a?(String) && value.strip.empty?

          merged[key] = value
        end
        merged
      end
      private_class_method :merge_non_empty_params

      def extract_nested_data(payload)
        data = Runtime::Util.extract_hash(payload)
        inner = data[:data]
        inner.is_a?(Hash) ? Runtime::Util.extract_hash(inner) : nil
      end
      private_class_method :extract_nested_data

      def fallback_tool_message(formatter, tool_data)
        return nil unless formatter.to_s == "flight_status"

        data = extract_nested_data(tool_data) || {}
        flight = data[:flight].is_a?(Hash) ? Runtime::Util.extract_hash(data[:flight]) : {}
        return "Статус рейса не найден." if flight.empty?

        fn = flight[:flight_number].to_s.strip
        fn = "рейс" if fn.empty?
        src = flight[:from].to_s.strip
        src = "?" if src.empty?
        dst = flight[:to].to_s.strip
        dst = "?" if dst.empty?
        dep = flight[:departure_time].to_s.strip
        arr = flight[:arrival_time].to_s.strip
        status = flight[:status].to_s.strip.upcase
        dep_short = dep.length >= 16 && dep.include?("T") ? dep[11, 5] : dep
        arr_short = arr.length >= 16 && arr.include?("T") ? arr[11, 5] : arr
        status_map = {
          "ON_TIME" => "вовремя",
          "DELAYED" => "задерживается",
          "CANCELLED" => "отменен"
        }
        status_text = status_map[status]
        status_text = status.downcase unless status_text || status.empty?
        status_text = "неизвестен" if status_text.to_s.empty?
        "Рейс #{fn} (#{src} → #{dst}), вылет #{dep_short}, прибытие #{arr_short}. Статус: #{status_text}."
      end
      private_class_method :fallback_tool_message

      def normalize_route_args(extracted, pos_data, airports_data)
        out = {}
        %i[from_lat from_lon to_lat to_lon].each do |key|
          value = Runtime::Util.float(Runtime::Util.extract_hash(extracted)[key])
          out[key] = value if value
        end
        out[:from_lat] ||= Runtime::Util.float(pos_data[:lat])
        out[:from_lon] ||= Runtime::Util.float(pos_data[:lon])

        airports = Array(airports_data[:airports])
        first = airports.first.is_a?(Hash) ? Runtime::Util.extract_hash(airports.first) : {}
        out[:to_lat] ||= Runtime::Util.float(first[:lat])
        out[:to_lon] ||= Runtime::Util.float(first[:lon])

        required = %i[from_lat from_lon to_lat to_lon]
        return nil unless required.all? { |key| out.key?(key) }

        required.each_with_object({}) { |key, acc| acc[key] = out[key] }
      end
      private_class_method :normalize_route_args

      def entity_label(entity, fallback: "объект")
        payload = Runtime::Util.extract_hash(entity)
        title = [payload[:label], payload[:name], payload[:title]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
        code = [payload[:code], payload[:id], payload[:key]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
        return "#{title} (#{code})" unless title.empty? || code.empty?
        return title unless title.empty?
        return code unless code.empty?

        fallback
      end
      private_class_method :entity_label

      def tokenize_label(label)
        compact = label.to_s.strip
        return [] if compact.empty?

        compact.split(/[()\s,.;:]+/).reject(&:empty?)
      end
      private_class_method :tokenize_label

      def looks_like_entity(payload)
        data = Runtime::Util.extract_hash(payload)
        %i[label name title code id key].any? do |key|
          value = data[key]
          next !value.nil? && !value.is_a?(Hash) && !value.is_a?(Array) if %i[id code key].include?(key)

          value.is_a?(String) && !value.strip.empty?
        end
      end
      private_class_method :looks_like_entity

      def extract_entities_from_artifacts(context_extra)
        artifact = Runtime::Util.extract_hash(context_extra[:artifact_memory])
        return [] if artifact.empty?

        entities = []
        artifact.each do |key, value|
          if value.is_a?(Array)
            value.first(10).each_with_index do |item, idx|
              next unless item.is_a?(Hash) && looks_like_entity(item)

              entities << { label: entity_label(item, fallback: "#{key}[#{idx + 1}]"), source: key.to_s, raw: Runtime::Util.extract_hash(item) }
            end
          elsif value.is_a?(Hash) && looks_like_entity(value)
            entities << { label: entity_label(value, fallback: key.to_s), source: key.to_s, raw: Runtime::Util.extract_hash(value) }
          end
        end

        seen = {}
        entities.each_with_object([]) do |row, out|
          label = row[:label].to_s.strip
          next if label.empty?

          lower = label.downcase
          next if seen[lower]

          seen[lower] = true
          out << row
        end
      end
      private_class_method :extract_entities_from_artifacts

      def explicit_entity_mentions(text, entities)
        clean = text.to_s
        lower = clean.downcase
        entities.select do |entity|
          label = entity[:label].to_s.strip
          next false if label.empty?
          next true if lower.include?(label.downcase)

          tokenize_label(label).any? { |token| /\b#{Regexp.escape(token)}\b/i.match?(clean) }
        end
      end
      private_class_method :explicit_entity_mentions

      def last_assistant_turn(dialog_context)
        assistant_lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?).select { |line| line.start_with?("- Assistant:") }
        assistant_lines.last.to_s
      end
      private_class_method :last_assistant_turn

      def pick_primary_by_recent_assistant(entities, dialog_context)
        last = last_assistant_turn(dialog_context)
        return nil if last.empty?

        matches = entities.select do |entity|
          label = entity[:label].to_s.strip
          next false if label.empty?
          next true if last.downcase.include?(label.downcase)

          tokenize_label(label).any? { |token| last.downcase.include?(token.downcase) }
        end
        matches.length == 1 ? matches.first : nil
      end
      private_class_method :pick_primary_by_recent_assistant

      def resolve_entity_reference(text, entities, dialog_context:)
        mentions = explicit_entity_mentions(text, entities)
        if mentions.length == 1
          label = entity_label(mentions.first)
          return ["single", mentions, "Запрос относится к сущности #{label}."]
        end
        if mentions.length > 1
          labels = mentions.first(5).map { |item| entity_label(item) }.join(", ")
          return ["multi", mentions.first(5), "Запрос относится к нескольким сущностям: #{labels}."]
        end

        plural = PLURAL_REF_RE.match?(text.to_s)
        singular = SINGULAR_REF_RE.match?(text.to_s)
        if plural && !entities.empty?
          labels = entities.first(5).map { |item| entity_label(item) }.join(", ")
          return ["multi", entities.first(5), "Запрос относится к сущностям из контекста: #{labels}."]
        end
        if singular
          primary = pick_primary_by_recent_assistant(entities, dialog_context)
          if primary
            label = entity_label(primary)
            return ["single", [primary], "Запрос относится к последней фокусной сущности: #{label}."]
          end
          if entities.length == 1
            label = entity_label(entities.first)
            return ["single", entities.first(1), "В контексте только одна сущность: #{label}."]
          end
          return ["clarify", entities.first(5), "Единственное число при нескольких сущностях требует уточнения."] if entities.length > 1
        end
        if entities.length == 1
          label = entity_label(entities.first)
          return ["single", entities.first(1), "В контексте только одна сущность: #{label}."]
        end

        ["none", [], ""]
      end
      private_class_method :resolve_entity_reference

      def clarify_entity_message(entities)
        return "Уточните, о каком объекте речь." if entities.empty?

        "Уточните, о каком объекте речь: #{entities.first(5).map { |item| entity_label(item) }.join(', ')}."
      end
      private_class_method :clarify_entity_message

      def fact_query?(text)
        clean = text.to_s.strip
        !clean.empty? && (FACT_QUERY_RE.match?(clean) || YEAR_QUERY_RE.match?(clean))
      end
      private_class_method :fact_query?

      def year_query?(text)
        clean = text.to_s.strip
        !clean.empty? && YEAR_QUERY_RE.match?(clean)
      end
      private_class_method :year_query?

      def contains_year?(text)
        YEAR_VALUE_RE.match?(text.to_s)
      end
      private_class_method :contains_year?

      def contains_context_only_refusal?(text)
        lower = text.to_s.downcase
        !lower.empty? && CONTEXT_ONLY_REFUSAL_HINTS.any? { |marker| lower.include?(marker) }
      end
      private_class_method :contains_context_only_refusal?

      def mentions_resolved_entities?(text, resolved_entities)
        return true if resolved_entities.empty?

        clean = text.to_s
        return false if clean.empty?

        hits = resolved_entities.first(5).count do |entity|
          label = entity_label(entity).strip
          next false if label.empty?
          next true if clean.downcase.include?(label.downcase)

          tokenize_label(label).select { |token| token.length >= 3 }.any? { |token| /\b#{Regexp.escape(token)}\b/i.match?(clean) }
        end

        resolved_entities.length <= 1 ? hits >= 1 : hits >= [2, resolved_entities.length].min
      end
      private_class_method :mentions_resolved_entities?

      def response_quality_score(user_text:, response_text:, resolved_mode:, resolved_entities:)
        text = response_text.to_s.strip
        return 0 if text.empty?

        score = 1
        score += 2 unless contains_context_only_refusal?(text)
        score += 2 if year_query?(user_text) && contains_year?(text)
        score += 1 if %w[single multi].include?(resolved_mode) && mentions_resolved_entities?(text, resolved_entities)
        score
      end
      private_class_method :response_quality_score

      def needs_knowledge_retry(user_text:, response_text:, resolved_mode:, resolved_entities:)
        text = response_text.to_s.strip
        return true if text.empty?
        return true if contains_context_only_refusal?(text)
        return true if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
        return true if year_query?(user_text) && !contains_year?(text)
        return response_quality_score(user_text: user_text, response_text: text, resolved_mode: resolved_mode, resolved_entities: resolved_entities) < 4 if fact_query?(user_text)

        false
      end
      private_class_method :needs_knowledge_retry

      def retry_reason(user_text:, response_text:, resolved_mode:, resolved_entities:)
        text = response_text.to_s.strip
        return "empty_response" if text.empty?
        return "context_only_refusal" if contains_context_only_refusal?(text)
        return "missing_year_for_year_query" if year_query?(user_text) && !contains_year?(text)
        return "missing_resolved_entity_reference" if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
        return "low_quality_fact_answer" if fact_query?(user_text)

        "generic_secondary_pass"
      end
      private_class_method :retry_reason

      def short_dialog_context(dialog_context, max_lines: 10, max_chars: 2400)
        lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?)
        return "" if lines.empty?

        tail = lines.last(max_lines).join("\n")
        tail.length <= max_chars ? tail : tail[-max_chars..]
      end
      private_class_method :short_dialog_context

      def retry_context_artifacts(context_artifacts:, resolved_entities:)
        return context_artifacts if resolved_entities.empty?

        resolved_raw = resolved_entities.first(5).filter_map do |row|
          raw = Runtime::Util.extract_hash(row[:raw])
          raw unless raw.empty?
        end
        return context_artifacts if resolved_raw.empty?

        { resolved_entities: resolved_raw }
      end
      private_class_method :retry_context_artifacts
    end
  end
end

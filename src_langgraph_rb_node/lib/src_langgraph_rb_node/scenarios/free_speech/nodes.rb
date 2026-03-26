# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    module FreeSpeech
      class Nodes < BaseNodes
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

        TASK = "Побеседуй с пользователем в свободной форме.\n" \
               "Отвечай кратко, по-русски, дружелюбно и по делу.\n" \
               "Если вопрос непонятен, задай уточняющий вопрос.\n" \
               "Используй context_artifacts и dialog_context для референций вроде 'он/этот' и 'они/эти'.\n" \
               "При resolved_reference_mode=single не задавай повторный вопрос о том, что имелось в виду.\n" \
               "При resolved_reference_mode=multi и запросе во множественном числе отвечай по каждой сущности из resolved_entities.\n" \
               "Используй не только контекст диалога, но и общие знания модели.\n" \
               "Если в знании не уверен, явно укажи неопределенность."
        SCENARIO_CONTEXT = "Свободный диалог без сценария.\n" \
                           "Инструменты не используются.\n" \
                           "Цель — помочь пользователю и поддерживать разговор."
        FALLBACK_MESSAGE = "Сервис ответов временно недоступен. Попробуйте повторить запрос."
        KNOWLEDGE_RETRY_TASK_SUFFIX = "Если вопрос пользователя требует фактов, не ограничивайся только полями из context_artifacts.\n" \
                                      "Используй общие знания модели вместе с контекстом диалога.\n" \
                                      "Считай context_artifacts подсказками, а не ограничением знаний.\n" \
                                      "Для вопросов про даты/историю/авторство используй знания модели, даже если в context_artifacts нет этих данных.\n" \
                                      "Не отвечай шаблоном о нехватке данных, если факт можно дать из общих знаний.\n" \
                                      "Если уверенность низкая, прямо укажи это в ответе."

        def prepare_context(state)
          entities = extract_entities_from_artifacts(Runtime::Util.extract_hash(state[:context_extra]))
          resolved_mode, resolved_entities, resolved_hint = resolve_entity_reference(
            state.dig(:req, :text).to_s,
            entities,
            dialog_context: state[:dialog_context].to_s
          )

          out = {
            resolved_mode: resolved_mode,
            resolved_entities: resolved_entities,
            resolved_hint: resolved_hint,
            prepare_status: resolved_mode == "clarify" ? "clarify" : "continue"
          }
          out[:clarify_message] = clarify_entity_message(resolved_entities) if resolved_mode == "clarify"
          out
        end

        def route_after_prepare(state)
          if state[:prepare_status] == "clarify"
            AsyncGraph::Command.goto(:clarify_reference)
          else
            AsyncGraph::Command.goto(:compose_response)
          end
        end

        def clarify_reference(state)
          { response: done_response(state.fetch(:req), state[:clarify_message]) }
        end

        def compose_response(state, await)
          req = state.fetch(:req)
          primary_input = {
            task: TASK,
            user_message: req[:text],
            tool_results: [],
            scenario_context: SCENARIO_CONTEXT,
            dialog_context: state[:dialog_context].to_s,
            context_artifacts: Runtime::Util.extract_hash(state[:context_artifacts]),
            resolved_reference_mode: %w[single multi].include?(state[:resolved_mode]) ? state[:resolved_mode] : "none",
            resolved_entities: Array(state[:resolved_entities]).first(5),
            resolved_hint: state[:resolved_hint].to_s,
            free_speech_pass: "primary"
          }
          # Здесь сценарий только объявляет LLM-запрос.
          # Дальше AsyncGraph приостанавливает ноду и передает запрос в runtime stack.
          primary_resp = await.call(
            "free_speech_primary",
            :llm,
            mode: "final_response",
            input_data: primary_input,
            constraints: { temperature: 0.4 }
          )

          primary_text = extract_llm_text(primary_resp)
          return { response_message: FALLBACK_MESSAGE } if primary_text.empty?

          unless needs_knowledge_retry(
            user_text: req[:text].to_s,
            response_text: primary_text,
            resolved_mode: state[:resolved_mode].to_s,
            resolved_entities: Array(state[:resolved_entities])
          )
            return { response_message: primary_text }
          end

          secondary_resp = await.call(
            "free_speech_retry",
            :llm,
            mode: "final_response",
            input_data: primary_input.merge(
              task: [TASK, KNOWLEDGE_RETRY_TASK_SUFFIX].join("\n"),
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
            ),
            constraints: { temperature: 0.3 }
          )
          secondary_text = extract_llm_text(secondary_resp)

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
          best_text = primary_text if best_text.to_s.empty?
          best_text = FALLBACK_MESSAGE if best_text.to_s.empty?
          { response_message: best_text }
        end

        def emit_final_response(state)
          { response: done_response(state.fetch(:req), state[:response_message]) }
        end

        private

        def entity_label(entity, fallback: "объект")
          payload = Runtime::Util.extract_hash(entity)
          title = [payload[:label], payload[:name], payload[:title]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
          code = [payload[:code], payload[:id], payload[:key]].map { |item| item.to_s.strip }.find { |item| !item.empty? }.to_s
          return "#{title} (#{code})" unless title.empty? || code.empty?
          return title unless title.empty?
          return code unless code.empty?

          fallback
        end

        def tokenize_label(label)
          compact = label.to_s.strip
          return [] if compact.empty?

          compact.split(/[()\s,.;:]+/).reject(&:empty?)
        end

        def looks_like_entity(payload)
          data = Runtime::Util.extract_hash(payload)
          %i[label name title code id key].any? do |key|
            value = data[key]
            next !value.nil? && !value.is_a?(Hash) && !value.is_a?(Array) if %i[id code key].include?(key)

            value.is_a?(String) && !value.strip.empty?
          end
        end

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

        def last_assistant_turn(dialog_context)
          assistant_lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?).select { |line| line.start_with?("- Assistant:") }
          assistant_lines.last.to_s
        end

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

        def clarify_entity_message(entities)
          return "Уточните, о каком объекте речь." if entities.empty?

          "Уточните, о каком объекте речь: #{entities.first(5).map { |item| entity_label(item) }.join(', ')}."
        end

        def fact_query?(text)
          clean = text.to_s.strip
          !clean.empty? && (FACT_QUERY_RE.match?(clean) || YEAR_QUERY_RE.match?(clean))
        end

        def year_query?(text)
          clean = text.to_s.strip
          !clean.empty? && YEAR_QUERY_RE.match?(clean)
        end

        def contains_year?(text)
          YEAR_VALUE_RE.match?(text.to_s)
        end

        def contains_context_only_refusal?(text)
          lower = text.to_s.downcase
          !lower.empty? && CONTEXT_ONLY_REFUSAL_HINTS.any? { |marker| lower.include?(marker) }
        end

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

        def response_quality_score(user_text:, response_text:, resolved_mode:, resolved_entities:)
          text = response_text.to_s.strip
          return 0 if text.empty?

          score = 1
          score += 2 unless contains_context_only_refusal?(text)
          score += 2 if year_query?(user_text) && contains_year?(text)
          score += 1 if %w[single multi].include?(resolved_mode) && mentions_resolved_entities?(text, resolved_entities)
          score
        end

        def needs_knowledge_retry(user_text:, response_text:, resolved_mode:, resolved_entities:)
          text = response_text.to_s.strip
          return true if text.empty?
          return true if contains_context_only_refusal?(text)
          return true if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
          return true if year_query?(user_text) && !contains_year?(text)
          return response_quality_score(user_text:, response_text: text, resolved_mode:, resolved_entities:) < 4 if fact_query?(user_text)

          false
        end

        def retry_reason(user_text:, response_text:, resolved_mode:, resolved_entities:)
          text = response_text.to_s.strip
          return "empty_response" if text.empty?
          return "context_only_refusal" if contains_context_only_refusal?(text)
          return "missing_year_for_year_query" if year_query?(user_text) && !contains_year?(text)
          return "missing_resolved_entity_reference" if %w[single multi].include?(resolved_mode) && !mentions_resolved_entities?(text, resolved_entities)
          return "low_quality_fact_answer" if fact_query?(user_text)

          "generic_secondary_pass"
        end

        def short_dialog_context(dialog_context, max_lines: 10, max_chars: 2400)
          lines = dialog_context.to_s.lines.map(&:strip).reject(&:empty?)
          return "" if lines.empty?

          tail = lines.last(max_lines).join("\n")
          tail.length <= max_chars ? tail : tail[-max_chars..]
        end

        def retry_context_artifacts(context_artifacts:, resolved_entities:)
          return context_artifacts if resolved_entities.empty?

          resolved_raw = resolved_entities.first(5).filter_map do |row|
            raw = Runtime::Util.extract_hash(row[:raw])
            raw unless raw.empty?
          end
          return context_artifacts if resolved_raw.empty?

          { resolved_entities: resolved_raw }
        end
      end
    end
  end
end

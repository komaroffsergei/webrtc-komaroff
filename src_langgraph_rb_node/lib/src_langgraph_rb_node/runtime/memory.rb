# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    module Memory
      DEFAULT_MEMORY_CONTEXT_KEY = "dialog_memory"
      DEFAULT_ARTIFACT_CONTEXT_KEY = "artifact_memory"
      module_function

      def memory_from_context(context)
        base = context.is_a?(Hash) ? Runtime::Util.extract_hash(context) : {}
        extra = base.each_with_object({}) do |(key, value), out|
          out[key] = value unless key.to_s == DEFAULT_MEMORY_CONTEXT_KEY
        end
        payload = Runtime::Util.extract_hash(base[DEFAULT_MEMORY_CONTEXT_KEY.to_sym] || base[DEFAULT_MEMORY_CONTEXT_KEY])
        summary = (payload[:summary] || "").to_s.strip
        recent = normalize_turns(payload[:recent_turns])
        [summary, recent, extra]
      end

      def context_with_memory(summary:, recent_turns:, extra:)
        out = Runtime::Util.extract_hash(extra)
        out[DEFAULT_MEMORY_CONTEXT_KEY.to_sym] = {
          summary: summary.to_s.strip,
          recent_turns: normalize_turns(recent_turns)
        }
        out
      end

      def apply_edit_rewrite(summary:, recent_turns:, edit_turn_id:, recent_messages_limit:, summary_max_chars:)
        return compact_memory(summary:, recent_turns:, recent_messages_limit:, summary_max_chars:) unless edit_turn_id

        idx = recent_turns.index { |turn| turn[:role] == "user" && turn[:turn_id] == edit_turn_id }
        return ["", []] unless idx

        compact_memory(
          summary: "",
          recent_turns: recent_turns[0...idx],
          recent_messages_limit: recent_messages_limit,
          summary_max_chars: summary_max_chars
        )
      end

      def compact_memory(summary:, recent_turns:, recent_messages_limit:, summary_max_chars:)
        normalized = normalize_turns(recent_turns)
        safe_limit = [2, recent_messages_limit.to_i].max
        safe_summary_max = [200, summary_max_chars.to_i].max
        return [trim_tail(summary, safe_summary_max), normalized] if normalized.length <= safe_limit

        overflow = normalized[0...-safe_limit]
        kept = normalized[-safe_limit..]
        [merge_summary(summary, overflow, safe_summary_max), kept]
      end

      def build_dialog_context(summary:, recent_turns:, extra:, max_chars:)
        sections = []
        artifact_block = artifact_context_block(extra)
        sections << artifact_block unless artifact_block.empty?
        sections << "Summary:\n#{summary.strip}" unless summary.to_s.strip.empty?
        unless recent_turns.empty?
          lines = recent_turns.map { |turn| "- #{role_label(turn[:role])}: #{turn[:text]}" }
          sections << "Recent turns:\n#{lines.join("\n")}"
        end
        trim_tail(sections.join("\n\n").strip, [300, max_chars.to_i].max)
      end

      def append_exchange(recent_turns:, user_turn_id:, user_text:, assistant_turn_id:, assistant_text:)
        out = normalize_turns(recent_turns)
        out << turn("user", user_turn_id, user_text)
        out << turn("assistant", assistant_turn_id, assistant_text) unless assistant_text.to_s.strip.empty?
        out
      end

      def extract_edit_turn_id(edit)
        Runtime::Util.text(Runtime::Util.extract_hash(edit)[:turn_id])
      end

      def response_message_text(resp)
        result = resp[:result]
        return result.strip if result.is_a?(String) && !result.strip.empty?

        payload = Runtime::Util.extract_hash(Runtime::Util.extract_hash(resp[:client_handler])[:payload])
        %i[message summary prompt].each do |key|
          value = payload[key]
          return value.strip if value.is_a?(String) && !value.strip.empty?
        end

        errors = Array(resp[:errors])
        first = Runtime::Util.extract_hash(errors.first)
        message = first[:message]
        message.is_a?(String) ? message.strip : ""
      end

      def prepare_dialog_memory(req:, recent_messages_limit:, summary_max_chars:, context_max_chars:)
        summary, recent_turns, extra = memory_from_context(req.dig(:runtime, :context))
        edit_turn_id = extract_edit_turn_id(req[:edit])
        summary, recent_turns = apply_edit_rewrite(
          summary: summary,
          recent_turns: recent_turns,
          edit_turn_id: edit_turn_id,
          recent_messages_limit: recent_messages_limit,
          summary_max_chars: summary_max_chars
        )
        extra.delete(DEFAULT_ARTIFACT_CONTEXT_KEY.to_sym) if edit_turn_id

        {
          summary: summary,
          recent_turns: recent_turns,
          context_extra: extra,
          dialog_context: build_dialog_context(
            summary: summary,
            recent_turns: recent_turns,
            extra: extra,
            max_chars: context_max_chars
          )
        }
      end

      def turn(role, turn_id, text)
        {
          role: role.to_s.strip.downcase == "assistant" ? "assistant" : "user",
          turn_id: turn_id.to_s.strip,
          text: text.to_s.strip
        }
      end
      private_class_method :turn

      def normalize_turns(raw)
        return [] unless raw.is_a?(Array)

        raw.filter_map do |row|
          next unless row.is_a?(Hash)

          item = Runtime::Util.extract_hash(row)
          role = item[:role].to_s.strip.downcase
          turn_id = item[:turn_id].to_s.strip
          text = item[:text].to_s.strip
          next unless %w[user assistant].include?(role) && !turn_id.empty? && !text.empty?

          { role: role, turn_id: turn_id, text: single_line(text, 1000) }
        end
      end
      private_class_method :normalize_turns

      def merge_summary(current, overflow, summary_max_chars)
        rows = overflow.map { |row| "#{role_label(row[:role])}: #{single_line(row[:text], 400)}" }
        merged = current.to_s.strip
        chunk = rows.join(" | ").strip
        return trim_tail(merged, summary_max_chars) if chunk.empty?

        trim_tail([merged, chunk].reject(&:empty?).join(" | "), summary_max_chars)
      end
      private_class_method :merge_summary

      def single_line(text, limit)
        one_line = text.to_s.split.join(" ")
        return one_line if one_line.length <= limit

        "#{one_line[0, [1, limit - 14].max]}...<truncated>"
      end
      private_class_method :single_line

      def trim_tail(text, max_chars)
        clean = text.to_s.strip
        return clean if clean.length <= max_chars

        "...#{clean[-max_chars..]}"
      end
      private_class_method :trim_tail

      def role_label(role)
        role == "user" ? "User" : "Assistant"
      end
      private_class_method :role_label

      def artifact_context_block(extra)
        return "" unless extra.is_a?(Hash)

        artifact = Runtime::Util.extract_hash(extra[DEFAULT_ARTIFACT_CONTEXT_KEY.to_sym] || extra[DEFAULT_ARTIFACT_CONTEXT_KEY])
        return "" if artifact.empty?

        lines = artifact.filter_map do |key, value|
          summary = artifact_value_summary(value)
          "- #{key}: #{summary}" unless summary.nil? || summary.empty?
        end
        return "" if lines.empty?

        "Context artifacts:\n#{lines.join("\n")}"
      end
      private_class_method :artifact_context_block

      def artifact_value_summary(value)
        if value.is_a?(Array)
          return "[]" if value.empty?

          items = value.first(5).filter_map { |row| artifact_value_brief(row) }
          return "list[#{value.length}]" if items.empty?

          suffix = value.length > 5 ? "; ..." : ""
          return "#{items.join('; ')}#{suffix}"
        end

        artifact_value_brief(value)
      end
      private_class_method :artifact_value_summary

      def artifact_value_brief(value)
        if value.is_a?(Hash)
          payload = Runtime::Util.extract_hash(value)
          label = artifact_entity_label(payload)
          return label unless label.empty?

          pairs = []
          payload.each do |key, item|
            scalar = artifact_scalar(item)
            next unless scalar

            pairs << "#{key}=#{scalar}"
            break if pairs.length >= 4
          end
          return pairs.join(", ") unless pairs.empty?

          return "object"
        end

        artifact_scalar(value).to_s
      end
      private_class_method :artifact_value_brief

      def artifact_entity_label(payload)
        label = payload[:label].to_s.strip
        label = payload[:name].to_s.strip if label.empty?
        label = payload[:title].to_s.strip if label.empty?
        code = payload[:code].to_s.strip
        ident = payload[:id].to_s.strip
        ident = payload[:key].to_s.strip if ident.empty?

        return "#{label} (#{code})" unless label.empty? || code.empty?
        return "#{label} (#{ident})" unless label.empty? || ident.empty? || ident == label
        return label unless label.empty?
        return code unless code.empty?
        return ident unless ident.empty?

        ""
      end
      private_class_method :artifact_entity_label

      def artifact_scalar(value)
        case value
        when nil
          nil
        when true
          "true"
        when false
          "false"
        when Numeric
          value.to_s
        when String
          clean = single_line(value, 80)
          clean.empty? ? nil : clean
        end
      end
      private_class_method :artifact_scalar
    end
  end
end

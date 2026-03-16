# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Contracts
      module Llm
        MODES = %w[routing_decision params_extract revise tool_decision tool_params final_response].freeze
        module_function

        def request(parent:, mode:, input:, constraints: {})
          raise ArgumentError, "unsupported LLM mode #{mode.inspect}" unless MODES.include?(mode.to_s)

          {
            trace_id: parent.fetch(:trace_id),
            correlation_id: parent.fetch(:correlation_id),
            request_id: Runtime::Util.generate_uuid,
            session_id: parent[:session_id],
            ts_ms: Common.now_ts_ms,
            mode: mode.to_s,
            input: Runtime::Util.extract_hash(input),
            constraints: Runtime::Util.extract_hash(constraints)
          }
        end

        def normalize_response(payload, request:)
          raw = Runtime::Util.extract_hash(payload)
          return error_response(request:, code: "invalid_llm_response", message: "LLM response must be a JSON object") if raw.empty?

          ok = !!raw[:ok]
          data = raw[:data]
          data = Runtime::Util.extract_hash(data) if data.is_a?(Hash)
          error = raw[:error]
          error = Runtime::Util.extract_hash(error) if error.is_a?(Hash)

          {
            trace_id: raw[:trace_id] || request.fetch(:trace_id),
            correlation_id: raw[:correlation_id] || request.fetch(:correlation_id),
            request_id: raw[:request_id] || request.fetch(:request_id),
            session_id: raw.key?(:session_id) ? raw[:session_id] : request[:session_id],
            ts_ms: Runtime::Util.integer(raw[:ts_ms], default: Common.now_ts_ms),
            ok: ok,
            data: ok ? (data.is_a?(Hash) ? data : nil) : nil,
            error: ok ? nil : (error.is_a?(Hash) ? error : Common.error_info(code: "llm_failed", message: "Unknown LLM failure"))
          }
        end

        def error_response(request:, code:, message:)
          {
            trace_id: request.fetch(:trace_id),
            correlation_id: request.fetch(:correlation_id),
            request_id: request.fetch(:request_id),
            session_id: request[:session_id],
            ts_ms: Common.now_ts_ms,
            ok: false,
            data: nil,
            error: Common.error_info(code:, message:)
          }
        end
      end
    end
  end
end

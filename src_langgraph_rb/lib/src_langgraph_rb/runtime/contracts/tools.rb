# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Contracts
      module Tools
        module_function

        def request(parent:, tool_name:, args:)
          {
            trace_id: parent.fetch(:trace_id),
            correlation_id: parent.fetch(:correlation_id),
            request_id: Runtime::Util.generate_uuid,
            session_id: parent[:session_id],
            ts_ms: Common.now_ts_ms,
            tool_name: Runtime::Util.require_non_empty_string!(tool_name, "tool_name"),
            args: Runtime::Util.extract_hash(args)
          }
        end

        def normalize_response(payload, request:)
          raw = Runtime::Util.extract_hash(payload)
          return error_response(request:, code: "invalid_tool_response", message: "Tool response must be a JSON object") if raw.empty?

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
            artifact_key: Runtime::Util.text(raw[:artifact_key]),
            data: ok ? data : (data.is_a?(Hash) ? data : nil),
            error: ok ? nil : (error.is_a?(Hash) ? error : Common.error_info(code: "tool_failed", message: "Unknown tool failure"))
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
            artifact_key: nil,
            data: nil,
            error: Common.error_info(code:, message:)
          }
        end
      end
    end
  end
end

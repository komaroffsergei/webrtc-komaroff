# frozen_string_literal: true

require "time"

module SrcLanggraphRb
  module Runtime
    module Contracts
      module Common
        module_function

        def now_ts_ms
          (Time.now.to_f * 1000).to_i
        end

        def validate_trace_envelope!(payload)
          data = Runtime::Util.extract_hash(payload)
          trace_id = Runtime::Util.require_uuid!(data[:trace_id], "trace_id")
          request_id = Runtime::Util.require_uuid!(data[:request_id], "request_id")
          correlation_id = data[:correlation_id]
          correlation_id = trace_id if correlation_id.nil?
          Runtime::Util.require_uuid!(correlation_id, "correlation_id")

          session_id = data[:session_id]
          Runtime::Util.require_uuid!(session_id, "session_id") unless session_id.nil?

          {
            trace_id: trace_id,
            request_id: request_id,
            correlation_id: correlation_id,
            session_id: session_id,
            ts_ms: Runtime::Util.require_positive_integer!(data[:ts_ms], "ts_ms")
          }
        end

        def validate_health_request!(payload)
          data = validate_trace_envelope!(payload)
          kind = Runtime::Util.text(Runtime::Util.extract_hash(payload)[:kind]) || "health"
          raise ArgumentError, "kind must be health" unless kind == "health"

          data.merge(kind: "health")
        end

        def error_info(code:, message:, details: nil)
          out = {
            code: Runtime::Util.require_non_empty_string!(code, "error code"),
            message: Runtime::Util.require_non_empty_string!(message, "error message")
          }
          out[:details] = Runtime::Util.extract_hash(details) if details.is_a?(Hash) && !details.empty?
          out
        end
      end
    end
  end
end

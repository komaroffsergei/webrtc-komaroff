# frozen_string_literal: true

module SrcLanggraphRb
  module Contracts
    class LlmRequest < TraceEnvelope
      MODES = %w[routing_decision params_extract revise tool_decision tool_params final_response].freeze

      attr_reader :mode, :input, :constraints

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, mode:, input:, constraints: {})
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @mode = Validation.string!(mode, "mode")
        raise ValidationError, "unsupported llm mode #{mode}" unless MODES.include?(@mode)

        @input = Validation.deep_copy_hash(input)
        @constraints = Validation.deep_copy_hash(constraints)
      end

      def to_h
        trace_h.merge(
          mode: mode,
          input: input,
          constraints: constraints
        )
      end
    end

    class LlmResponse < TraceEnvelope
      attr_reader :ok, :data, :error

      def self.from_h(data)
        source = Validation.hash!(data, "llm response")
        new(
          trace_id: source["trace_id"] || source[:trace_id],
          correlation_id: source["correlation_id"] || source[:correlation_id],
          request_id: source["request_id"] || source[:request_id],
          session_id: source["session_id"] || source[:session_id],
          ts_ms: source["ts_ms"] || source[:ts_ms],
          ok: source["ok"] || source[:ok],
          data: source["data"] || source[:data],
          error: source["error"] || source[:error]
        )
      end

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, ok:, data: nil, error: nil)
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @ok = Validation.bool(ok)
        @data = data.is_a?(Hash) ? Validation.deep_copy_hash(data) : nil
        @error = error.is_a?(ErrorInfo) ? error : (error ? ErrorInfo.from_h(error) : nil)
      end
    end
  end
end

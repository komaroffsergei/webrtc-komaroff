# frozen_string_literal: true

module SrcLanggraphRb
  module Contracts
    class ToolCallRequest < TraceEnvelope
      attr_reader :tool_name, :args

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, tool_name:, args: {})
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @tool_name = Validation.string!(tool_name, "tool_name")
        @args = Validation.deep_copy_hash(args)
      end

      def to_h
        trace_h.merge(
          tool_name: tool_name,
          args: args
        )
      end
    end

    class ToolCallResponse < TraceEnvelope
      attr_reader :ok, :artifact_key, :data, :error

      def self.from_h(data)
        source = Validation.hash!(data, "tool response")
        new(
          trace_id: source["trace_id"] || source[:trace_id],
          correlation_id: source["correlation_id"] || source[:correlation_id],
          request_id: source["request_id"] || source[:request_id],
          session_id: source["session_id"] || source[:session_id],
          ts_ms: source["ts_ms"] || source[:ts_ms],
          ok: source["ok"] || source[:ok],
          artifact_key: source["artifact_key"] || source[:artifact_key],
          data: source["data"] || source[:data],
          error: source["error"] || source[:error]
        )
      end

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, ok:, artifact_key: nil, data: nil, error: nil)
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @ok = Validation.bool(ok)
        @artifact_key = Validation.optional_string(artifact_key)
        @data = data.is_a?(Hash) ? Validation.deep_copy_hash(data) : nil
        @error = error.is_a?(ErrorInfo) ? error : (error ? ErrorInfo.from_h(error) : nil)
      end
    end
  end
end

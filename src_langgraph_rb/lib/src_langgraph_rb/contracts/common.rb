# frozen_string_literal: true

module SrcLanggraphRb
  module Contracts
    def self.now_ts_ms
      (Time.now.to_f * 1000).to_i
    end

    class ErrorInfo
      attr_reader :code, :message, :details

      def self.from_h(data)
        source = Validation.hash!(data, "error")
        new(
          code: Validation.string!(source["code"] || source[:code], "error.code"),
          message: Validation.string!(source["message"] || source[:message], "error.message"),
          details: Validation.deep_copy_hash(source["details"] || source[:details])
        )
      end

      def initialize(code:, message:, details: nil)
        @code = Validation.string!(code, "error.code")
        @message = Validation.string!(message, "error.message")
        @details = details.is_a?(Hash) ? Validation.deep_copy_hash(details) : nil
      end

      def to_h
        {
          code: code,
          message: message,
          details: details
        }
      end
    end

    class TraceEnvelope
      attr_reader :trace_id, :request_id, :correlation_id, :session_id, :ts_ms

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:)
        @trace_id = Validation.uuid!(trace_id, "trace_id")
        @request_id = Validation.uuid!(request_id, "request_id")
        @correlation_id = Validation.optional_uuid(correlation_id) || @trace_id
        @session_id = Validation.optional_uuid(session_id)
        @ts_ms = Validation.integer!(ts_ms, "ts_ms")
      end

      def trace_h
        {
          trace_id: trace_id,
          correlation_id: correlation_id,
          request_id: request_id,
          session_id: session_id,
          ts_ms: ts_ms
        }
      end
    end

    class ServiceHealthRequest < TraceEnvelope
      attr_reader :kind

      def self.from_h(data)
        source = Validation.hash!(data, "health request")
        new(
          trace_id: source["trace_id"] || source[:trace_id],
          correlation_id: source["correlation_id"] || source[:correlation_id],
          request_id: source["request_id"] || source[:request_id],
          session_id: source["session_id"] || source[:session_id],
          ts_ms: source["ts_ms"] || source[:ts_ms],
          kind: source["kind"] || source[:kind]
        )
      end

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, kind: "health")
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @kind = Validation.string!(kind, "kind")
        raise ValidationError, "kind must be health" unless @kind == "health"
      end

      def to_h
        trace_h.merge(kind: kind)
      end
    end

    class ServiceHealthResponse < TraceEnvelope
      attr_reader :ok, :status, :details, :error

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, ok:, status:, details: {}, error: nil)
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @ok = Validation.bool(ok)
        @status = Validation.string!(status, "status")
        raise ValidationError, "status must be healthy or unhealthy" unless %w[healthy unhealthy].include?(@status)

        @details = Validation.deep_copy_hash(details)
        @error = error.is_a?(ErrorInfo) ? error : (error ? ErrorInfo.from_h(error) : nil)
      end

      def to_h
        trace_h.merge(
          ok: ok,
          status: status,
          details: details,
          error: error&.to_h
        )
      end
    end
  end
end

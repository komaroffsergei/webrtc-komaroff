# frozen_string_literal: true

module SrcLanggraphRb
  module Contracts
    class WorkflowRuntimeState
      attr_reader :active_workflow_id, :pending, :context, :version

      def self.from_h(data)
        source = data.is_a?(Hash) ? data : {}
        new(
          active_workflow_id: source["active_workflow_id"] || source[:active_workflow_id],
          pending: source["pending"] || source[:pending],
          context: source["context"] || source[:context],
          version: source["version"] || source[:version] || 1
        )
      end

      def initialize(active_workflow_id: nil, pending: nil, context: nil, version: 1)
        @active_workflow_id = Validation.optional_string(active_workflow_id)
        @pending = pending.is_a?(Hash) ? Validation.deep_copy_hash(pending) : nil
        @context = context.is_a?(Hash) ? Validation.deep_copy_hash(context) : nil
        @version = Validation.integer!(version, "runtime.version")
      end

      def to_h
        {
          active_workflow_id: active_workflow_id,
          pending: pending,
          context: context,
          version: version
        }
      end

      def with(active_workflow_id: self.active_workflow_id, pending: self.pending, context: self.context, version: self.version)
        self.class.new(active_workflow_id:, pending:, context:, version:)
      end
    end

    class WorkflowRunRequest < TraceEnvelope
      attr_reader :text, :turn_id, :edit, :runtime

      def self.from_h(data)
        source = Validation.hash!(data, "workflow request")
        new(
          trace_id: source["trace_id"] || source[:trace_id],
          correlation_id: source["correlation_id"] || source[:correlation_id],
          request_id: source["request_id"] || source[:request_id],
          session_id: source["session_id"] || source[:session_id],
          ts_ms: source["ts_ms"] || source[:ts_ms],
          text: source["text"] || source[:text],
          turn_id: source["turn_id"] || source[:turn_id],
          edit: source["edit"] || source[:edit],
          runtime: WorkflowRuntimeState.from_h(source["runtime"] || source[:runtime])
        )
      end

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, text:, turn_id: nil, edit: nil, runtime: WorkflowRuntimeState.new)
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @text = Validation.string!(text, "text")
        @turn_id = Validation.optional_string(turn_id)
        @edit = edit.is_a?(Hash) ? Validation.deep_copy_hash(edit) : nil
        @runtime = runtime.is_a?(WorkflowRuntimeState) ? runtime : WorkflowRuntimeState.from_h(runtime)
      end

      def to_h
        trace_h.merge(
          text: text,
          turn_id: turn_id,
          edit: edit,
          runtime: runtime.to_h
        )
      end
    end

    class WorkflowRunResponse < TraceEnvelope
      STATUSES = %w[RUNNING PARTIAL DONE FAILED].freeze

      attr_reader :status, :result, :client_handler, :client_events, :next_runtime, :errors

      def self.from_h(data)
        source = Validation.hash!(data, "workflow response")
        new(
          trace_id: source["trace_id"] || source[:trace_id],
          correlation_id: source["correlation_id"] || source[:correlation_id],
          request_id: source["request_id"] || source[:request_id],
          session_id: source["session_id"] || source[:session_id],
          ts_ms: source["ts_ms"] || source[:ts_ms],
          status: source["status"] || source[:status],
          result: source["result"] || source[:result] || "",
          client_handler: source["client_handler"] || source[:client_handler],
          client_events: source["client_events"] || source[:client_events],
          next_runtime: WorkflowRuntimeState.from_h(source["next_runtime"] || source[:next_runtime]),
          errors: Validation.array(source["errors"] || source[:errors]).map { |row| ErrorInfo.from_h(row) }
        )
      end

      def initialize(trace_id:, request_id:, correlation_id: nil, session_id: nil, ts_ms:, status:, result: "", client_handler: {}, client_events: [], next_runtime: WorkflowRuntimeState.new, errors: [])
        super(trace_id:, request_id:, correlation_id:, session_id:, ts_ms:)
        @status = Validation.string!(status, "status")
        raise ValidationError, "status must be one of #{STATUSES.join(', ')}" unless STATUSES.include?(@status)

        @result = result.is_a?(String) ? result : result.to_s
        @client_handler = client_handler.is_a?(Hash) ? Validation.deep_copy_hash(client_handler) : {}
        @client_events = Validation.array(client_events).map { |row| row.is_a?(Hash) ? Validation.deep_copy_hash(row) : row }
        @next_runtime = next_runtime.is_a?(WorkflowRuntimeState) ? next_runtime : WorkflowRuntimeState.from_h(next_runtime)
        @errors = Validation.array(errors).map { |row| row.is_a?(ErrorInfo) ? row : ErrorInfo.from_h(row) }
      end

      def to_h
        trace_h.merge(
          status: status,
          result: result,
          client_handler: client_handler,
          client_events: client_events,
          next_runtime: next_runtime.to_h,
          errors: errors.map(&:to_h)
        )
      end
    end
  end
end

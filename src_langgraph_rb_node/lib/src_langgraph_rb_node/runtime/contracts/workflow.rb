# frozen_string_literal: true

module SrcLanggraphRbNode
  module Runtime
    module Contracts
      module Workflow
        STATUSES = %w[RUNNING PARTIAL DONE FAILED].freeze
        module_function

        def validate_run_request!(payload)
          data = Common.validate_trace_envelope!(payload)
          raw = Runtime::Util.extract_hash(payload)
          runtime = normalize_runtime(raw[:runtime])
          text = Runtime::Util.require_non_empty_string!(raw[:text], "text")
          turn_id = Runtime::Util.text(raw[:turn_id])
          edit = raw[:edit]
          edit = Runtime::Util.extract_hash(edit) if edit.is_a?(Hash)
          edit = nil unless edit.is_a?(Hash) && !edit.empty?

          data.merge(text:, turn_id:, edit:, runtime:)
        end

        def normalize_runtime(value)
          raw = Runtime::Util.extract_hash(value)
          version = Runtime::Util.integer(raw[:version], default: 1)
          raise ArgumentError, "runtime.version must be >= 1" unless version && version >= 1

          {
            active_workflow_id: Runtime::Util.text(raw[:active_workflow_id]),
            pending: raw[:pending].is_a?(Hash) ? Runtime::Util.extract_hash(raw[:pending]) : nil,
            context: raw[:context].is_a?(Hash) ? Runtime::Util.extract_hash(raw[:context]) : nil,
            version: version
          }
        end

        def response(
          *,
          trace_id:,
          correlation_id:,
          request_id:,
          session_id:,
          ts_ms:,
          status:,
          result: "",
          client_handler: {},
          client_events: [],
          next_runtime: {},
          errors: []
        )
          raise ArgumentError, "unsupported workflow status #{status.inspect}" unless STATUSES.include?(status)

          {
            trace_id: trace_id,
            correlation_id: correlation_id,
            request_id: request_id,
            session_id: session_id,
            ts_ms: ts_ms,
            status: status,
            result: result.to_s,
            client_handler: Runtime::Util.extract_hash(client_handler),
            client_events: Array(client_events).map { |item| Runtime::Util.extract_hash(item) },
            next_runtime: normalize_runtime(next_runtime),
            errors: Array(errors).map { |item| Runtime::Util.extract_hash(item) }
          }
        end
      end
    end
  end
end

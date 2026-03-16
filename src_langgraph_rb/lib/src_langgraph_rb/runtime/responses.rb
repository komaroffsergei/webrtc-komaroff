# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    module Responses
      module_function

      def next_runtime(req, active_workflow_id: nil, pending: nil, context: nil)
        Contracts::Workflow.normalize_runtime(
          active_workflow_id: active_workflow_id,
          pending: pending,
          context: context,
          version: req.dig(:runtime, :version) || 1
        )
      end

      def done_response(req, message, client_events: nil)
        clean = message.to_s.strip
        clean = "Готово." if clean.empty?

        Contracts::Workflow.response(
          **base_response_kwargs(req),
          status: "DONE",
          result: clean,
          client_handler: { command: "SHOW_MESSAGE", payload: { message: clean } },
          client_events: client_events || [],
          next_runtime: next_runtime(req)
        )
      end

      def partial_response(req, prompt, active_workflow_id:, pending:)
        clean = prompt.to_s.strip

        Contracts::Workflow.response(
          **base_response_kwargs(req),
          status: "PARTIAL",
          result: clean,
          client_handler: { command: "ASK_USER_INPUT", payload: { message: clean } },
          next_runtime: next_runtime(
            req,
            active_workflow_id: active_workflow_id,
            pending: pending,
            context: req.dig(:runtime, :context)
          )
        )
      end

      def failed_response(req, code:, message:, runtime: nil, client_handler: nil)
        Contracts::Workflow.response(
          **base_response_kwargs(req),
          status: "FAILED",
          result: "",
          client_handler: client_handler || {},
          next_runtime: runtime || next_runtime(req),
          errors: [Contracts::Common.error_info(code:, message:)]
        )
      end

      def base_response_kwargs(req)
        {
          trace_id: req.fetch(:trace_id),
          correlation_id: req.fetch(:correlation_id),
          request_id: req.fetch(:request_id),
          session_id: req[:session_id],
          ts_ms: Contracts::Common.now_ts_ms
        }
      end
      private_class_method :base_response_kwargs
    end
  end
end

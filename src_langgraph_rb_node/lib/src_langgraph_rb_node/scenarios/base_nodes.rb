# frozen_string_literal: true

module SrcLanggraphRbNode
  module Scenarios
    class BaseNodes
      private

      def done_response(req, message, client_events: [])
        Runtime::Responses.done_response(req, message, client_events: client_events)
      end

      def partial_response(req, prompt, active_workflow_id:, pending:)
        Runtime::Responses.partial_response(
          req,
          prompt,
          active_workflow_id: active_workflow_id,
          pending: pending
        )
      end

      def failed_response(req, code:, message:, client_handler: nil)
        Runtime::Responses.failed_response(
          req,
          code: code,
          message: message,
          client_handler: client_handler
        )
      end

      def extract_llm_text(resp)
        data = Runtime::Util.extract_hash(resp[:data])
        value = data[:response_text]
        value.is_a?(String) ? value.strip : ""
      end

      def extract_nested_data(payload)
        data = Runtime::Util.extract_hash(payload)
        inner = data[:data]
        inner.is_a?(Hash) ? Runtime::Util.extract_hash(inner) : nil
      end
    end
  end
end

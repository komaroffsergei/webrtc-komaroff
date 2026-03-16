# frozen_string_literal: true

require "json"
require "nats"

module SrcLanggraphRb
  module Runtime
    class RuntimeIo
      attr_reader :nc, :llm_subject_prefix, :tools_subject_prefix, :user_id, :request_timeout_s

      def initialize(nc:, llm_subject_prefix:, tools_subject_prefix:, user_id:, request_timeout_s: 120.0)
        @nc = nc
        @llm_subject_prefix = llm_subject_prefix
        @tools_subject_prefix = tools_subject_prefix
        @user_id = user_id
        @request_timeout_s = request_timeout_s.to_f
      end

      def call_llm(parent:, mode:, input_data:, constraints: nil)
        req = Contracts::Llm.request(parent:, mode:, input: input_data, constraints: constraints || {})
        subject = "#{llm_subject_prefix}#{user_id}"
        raw = request_json(subject, JSON.generate(Runtime::Util.deep_stringify(req)))
        Contracts::Llm.normalize_response(raw, request: req)
      rescue StandardError => e
        request = req || fallback_request(parent)
        Contracts::Llm.error_response(
          request: request,
          code: "llm_transport_error",
          message: "LLM request failed for '#{subject}': #{e.message}"
        )
      end

      def call_tool(parent:, tool_name:, args:)
        req = Contracts::Tools.request(parent:, tool_name:, args:)
        subject = "#{tools_subject_prefix}#{tool_name}"
        raw = request_json(subject, JSON.generate(Runtime::Util.deep_stringify(req)))
        Contracts::Tools.normalize_response(raw, request: req)
      rescue StandardError => e
        request = req || fallback_request(parent)
        Contracts::Tools.error_response(
          request: request,
          code: "tool_transport_error",
          message: "Tool request failed for '#{subject}': #{e.message}"
        )
      end

      private

      def fallback_request(parent)
        trace = Runtime::Util.extract_hash(parent)
        {
          trace_id: trace[:trace_id] || Runtime::Util.generate_uuid,
          correlation_id: trace[:correlation_id] || trace[:trace_id] || Runtime::Util.generate_uuid,
          request_id: Runtime::Util.generate_uuid,
          session_id: trace[:session_id],
          ts_ms: Contracts::Common.now_ts_ms
        }
      end

      def request_json(subject, payload)
        msg = nc.request(subject, payload, timeout: request_timeout_s)
        data = JSON.parse(msg.data)
        raise ValidationError, "Invalid JSON response from #{subject}" unless data.is_a?(Hash)

        data
      end
    end
  end
end

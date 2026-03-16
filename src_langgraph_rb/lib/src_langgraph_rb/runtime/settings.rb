# frozen_string_literal: true

module SrcLanggraphRb
  module Runtime
    class Settings
      attr_reader :nats_url, :run_subject, :health_subject, :llm_subject_prefix, :tools_subject_prefix,
                  :user_id, :request_timeout_s, :memory_recent_messages, :memory_summary_max_chars,
                  :memory_context_max_chars, :stack_service_name, :max_reconnect_attempts,
                  :reconnect_time_wait

      def self.from_env(env = ENV)
        new(
          nats_url: env.fetch("NATS_URL", "nats://localhost:4222"),
          run_subject: env.fetch("NATS_WORKFLOW_RUN_SUBJECT", "nats.workflow.run.ruby"),
          health_subject: env.fetch("NATS_WORKFLOW_HEALTH_SUBJECT", "nats.workflow.health.ruby"),
          llm_subject_prefix: env.fetch("NATS_LLM_SUBJECT", "nats.llm."),
          tools_subject_prefix: env.fetch("NATS_TOOLS_PREFIX", "nats.tools."),
          user_id: env.fetch("USER_ID", "user123"),
          request_timeout_s: env.fetch("NATS_REQUEST_TIMEOUT_SECONDS", "60"),
          memory_recent_messages: env.fetch("MEMORY_RECENT_MESSAGES", "32"),
          memory_summary_max_chars: env.fetch("MEMORY_SUMMARY_MAX_CHARS", "12000"),
          memory_context_max_chars: env.fetch("MEMORY_CONTEXT_MAX_CHARS", "18000"),
          stack_service_name: env.fetch("STACK_SERVICE_NAME", "src_langgraph_rb"),
          max_reconnect_attempts: env.fetch("NATS_MAX_RECONNECT_ATTEMPTS", "-1"),
          reconnect_time_wait: env.fetch("NATS_RECONNECT_TIME_WAIT_SECONDS", "2")
        )
      end

      def initialize(
        nats_url:, run_subject:, health_subject:, llm_subject_prefix:, tools_subject_prefix:, user_id:,
        request_timeout_s:, memory_recent_messages:, memory_summary_max_chars:, memory_context_max_chars:,
        stack_service_name:, max_reconnect_attempts:, reconnect_time_wait:
      )
        @nats_url = nats_url
        @run_subject = run_subject
        @health_subject = health_subject
        @llm_subject_prefix = llm_subject_prefix
        @tools_subject_prefix = tools_subject_prefix
        @user_id = user_id
        @request_timeout_s = request_timeout_s.to_f
        @memory_recent_messages = memory_recent_messages.to_i
        @memory_summary_max_chars = memory_summary_max_chars.to_i
        @memory_context_max_chars = memory_context_max_chars.to_i
        @stack_service_name = stack_service_name
        @max_reconnect_attempts = max_reconnect_attempts.to_i
        @reconnect_time_wait = reconnect_time_wait.to_f
      end
    end
  end
end

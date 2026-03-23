#!/usr/bin/env ruby
# frozen_string_literal: true

require "json"
require "logger"
require "nats/client"

module SrcLanggraphRbNode
  module Runtime
    class Settings < Struct.new(
      :nats_url,
      :run_subject,
      :health_subject,
      :llm_subject_prefix,
      :tools_subject_prefix,
      :user_id,
      :request_timeout_s,
      :memory_recent_messages,
      :memory_summary_max_chars,
      :memory_context_max_chars,
      :stack_service_name,
      :max_reconnect_attempts,
      :reconnect_time_wait,
      keyword_init: true
    )
      def self.from_env(env = ENV)
        new(
          nats_url: env.fetch("NATS_URL", "nats://localhost:4222"),
          run_subject: env.fetch("NATS_WORKFLOW_RUN_SUBJECT", "nats.workflow.run.ruby.node"),
          health_subject: env.fetch("NATS_WORKFLOW_HEALTH_SUBJECT", "nats.workflow.health.ruby.node"),
          llm_subject_prefix: env.fetch("NATS_LLM_SUBJECT", "nats.llm."),
          tools_subject_prefix: env.fetch("NATS_TOOLS_PREFIX", "nats.tools."),
          user_id: env.fetch("USER_ID", "user123"),
          request_timeout_s: env.fetch("NATS_REQUEST_TIMEOUT_SECONDS", "60").to_f,
          memory_recent_messages: env.fetch("MEMORY_RECENT_MESSAGES", "32").to_i,
          memory_summary_max_chars: env.fetch("MEMORY_SUMMARY_MAX_CHARS", "12000").to_i,
          memory_context_max_chars: env.fetch("MEMORY_CONTEXT_MAX_CHARS", "18000").to_i,
          stack_service_name: env.fetch("STACK_SERVICE_NAME", "src_langgraph_rb_node"),
          max_reconnect_attempts: env.fetch("NATS_MAX_RECONNECT_ATTEMPTS", "-1").to_i,
          reconnect_time_wait: env.fetch("NATS_RECONNECT_TIME_WAIT_SECONDS", "2").to_f
        )
      end
    end

    class Service
      def self.run_from_env(env = ENV, logger: Logger.new($stdout))
        new(settings: Settings.from_env(env), logger: logger).run
      end

      def initialize(settings:, logger: Logger.new($stdout))
        @settings = settings
        @logger = logger
        @running = false
        @nc = nil
        @engine = nil
      end

      def run
        @nc = NATS.connect(
          servers: [@settings.nats_url],
          name: @settings.stack_service_name,
          max_reconnect_attempts: @settings.max_reconnect_attempts,
          reconnect_time_wait: @settings.reconnect_time_wait
        )

        io = RuntimeIo.new(
          nc: @nc,
          llm_subject_prefix: @settings.llm_subject_prefix,
          tools_subject_prefix: @settings.tools_subject_prefix,
          user_id: @settings.user_id,
          request_timeout_s: @settings.request_timeout_s
        )
        @engine = Engine.new(
          io: io,
          memory_recent_messages: @settings.memory_recent_messages,
          memory_summary_max_chars: @settings.memory_summary_max_chars,
          memory_context_max_chars: @settings.memory_context_max_chars
        )

        @nc.subscribe(@settings.run_subject) { |msg| safe_respond(msg, handle_run(msg)) }
        @nc.subscribe(@settings.health_subject) { |msg| safe_respond(msg, handle_health(msg)) }
        @logger.info("Subscribed to #{@settings.run_subject} and #{@settings.health_subject}")

        @running = true
        trap_signals
        sleep 0.1 while @running
      ensure
        @nc&.close
        @running = false
      end

      def stop
        @running = false
      end

      private

      def trap_signals
        %w[INT TERM].each do |signal|
          Signal.trap(signal) { stop }
        rescue ArgumentError
          nil
        end
      end

      def handle_run(msg)
        req = Contracts::Workflow.validate_run_request!(JSON.parse(msg.data))
        return missing_session_response(req) if req[:session_id].nil?

        JSON.generate(Runtime::Util.deep_stringify(@engine.run(req)))
      rescue StandardError => e
        invalid_run_response(msg.data, e)
      end

      def invalid_run_response(raw_payload, error)
        data = extract_request_metadata(raw_payload)
        response = Contracts::Workflow.response(
          trace_id: data[:trace_id],
          correlation_id: data[:correlation_id],
          request_id: data[:request_id],
          session_id: data[:session_id],
          ts_ms: Contracts::Common.now_ts_ms,
          status: "FAILED",
          result: "",
          client_handler: {},
          client_events: [],
          next_runtime: {},
          errors: [Contracts::Common.error_info(code: "workflow_failed", message: error.message)]
        )
        JSON.generate(Runtime::Util.deep_stringify(response))
      end

      def handle_health(msg)
        req = Contracts::Common.validate_health_request!(JSON.parse(msg.data))
        response = {
          trace_id: req[:trace_id],
          correlation_id: req[:correlation_id],
          request_id: req[:request_id],
          session_id: req[:session_id],
          ts_ms: Contracts::Common.now_ts_ms,
          ok: healthy?,
          status: healthy? ? "healthy" : "unhealthy",
          details: {
            service: "src_langgraph_rb_node",
            run_subject: @settings.run_subject
          },
          error: nil
        }
        JSON.generate(Runtime::Util.deep_stringify(response))
      rescue StandardError => e
        health_error_response(e)
      end

      def safe_respond(msg, payload)
        return if msg.reply.to_s.empty?

        msg.respond(payload)
      rescue StandardError => e
        @logger.error("Failed to respond on NATS: #{e.class}: #{e.message}")
      end

      def missing_session_response(req)
        JSON.generate(
          Runtime::Util.deep_stringify(
            Runtime::Responses.failed_response(
              req,
              code: "missing_session_id",
              message: "session_id is required",
              runtime: req[:runtime]
            )
          )
        )
      end

      def extract_request_metadata(raw_payload)
        payload = JSON.parse(raw_payload)
        data = Runtime::Util.extract_hash(payload)
        trace_id = Runtime::Util.uuid_string?(data[:trace_id]) ? data[:trace_id] : Runtime::Util.generate_uuid
        request_id = Runtime::Util.uuid_string?(data[:request_id]) ? data[:request_id] : Runtime::Util.generate_uuid

        {
          trace_id: trace_id,
          request_id: request_id,
          correlation_id: Runtime::Util.uuid_string?(data[:correlation_id]) ? data[:correlation_id] : trace_id,
          session_id: Runtime::Util.uuid_string?(data[:session_id]) ? data[:session_id] : nil
        }
      rescue JSON::ParserError
        {
          trace_id: Runtime::Util.generate_uuid,
          request_id: Runtime::Util.generate_uuid,
          correlation_id: Runtime::Util.generate_uuid,
          session_id: nil
        }
      end

      def health_error_response(error)
        response = {
          trace_id: Runtime::Util.generate_uuid,
          correlation_id: Runtime::Util.generate_uuid,
          request_id: Runtime::Util.generate_uuid,
          session_id: nil,
          ts_ms: Contracts::Common.now_ts_ms,
          ok: false,
          status: "unhealthy",
          details: { service: "src_langgraph_rb_node" },
          error: Contracts::Common.error_info(code: "health_failed", message: error.message)
        }
        JSON.generate(Runtime::Util.deep_stringify(response))
      end

      def healthy?
        !@nc.nil? && !@engine.nil?
      end
    end
  end
end

if $PROGRAM_NAME == __FILE__
  root = File.expand_path("../../..", __dir__)
  $LOAD_PATH.unshift(File.join(root, "lib"))
  service_file = File.expand_path(__FILE__)
  $LOADED_FEATURES << service_file unless $LOADED_FEATURES.include?(service_file)

  require "src_langgraph_rb_node"
  SrcLanggraphRbNode::Runtime::Service.run_from_env
end

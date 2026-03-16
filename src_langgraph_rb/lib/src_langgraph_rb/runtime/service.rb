# frozen_string_literal: true

require "logger"
require "nats/client"

module SrcLanggraphRb
  module Runtime
    class Service
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
        return JSON.generate(Runtime::Util.deep_stringify(Runtime::Responses.failed_response(req, code: "missing_session_id", message: "session_id is required", runtime: req[:runtime]))) if req[:session_id].nil?

        resp = @engine.run(req)
        JSON.generate(Runtime::Util.deep_stringify(resp))
      rescue StandardError => e
        invalid_run_response(msg.data, e)
      end

      def invalid_run_response(raw_payload, error)
        payload = JSON.parse(raw_payload) rescue {}
        data = Runtime::Util.extract_hash(payload)
        trace_id = Runtime::Util.uuid_string?(data[:trace_id]) ? data[:trace_id] : Runtime::Util.generate_uuid
        request_id = Runtime::Util.uuid_string?(data[:request_id]) ? data[:request_id] : Runtime::Util.generate_uuid
        correlation_id = Runtime::Util.uuid_string?(data[:correlation_id]) ? data[:correlation_id] : trace_id
        session_id = Runtime::Util.uuid_string?(data[:session_id]) ? data[:session_id] : nil
        response = Contracts::Workflow.response(
          trace_id: trace_id,
          correlation_id: correlation_id,
          request_id: request_id,
          session_id: session_id,
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
          ok: !@nc.nil? && !@engine.nil?,
          status: !@nc.nil? && !@engine.nil? ? "healthy" : "unhealthy",
          details: {
            service: "src_langgraph_rb",
            run_subject: @settings.run_subject
          },
          error: nil
        }
        JSON.generate(Runtime::Util.deep_stringify(response))
      rescue StandardError => e
        response = {
          trace_id: Runtime::Util.generate_uuid,
          correlation_id: Runtime::Util.generate_uuid,
          request_id: Runtime::Util.generate_uuid,
          session_id: nil,
          ts_ms: Contracts::Common.now_ts_ms,
          ok: false,
          status: "unhealthy",
          details: { service: "src_langgraph_rb" },
          error: Contracts::Common.error_info(code: "health_failed", message: e.message)
        }
        JSON.generate(Runtime::Util.deep_stringify(response))
      end

      def safe_respond(msg, payload)
        return if msg.reply.to_s.empty?

        msg.respond(payload)
      rescue StandardError => e
        @logger.error("Failed to respond on NATS: #{e.class}: #{e.message}")
      end
    end
  end
end

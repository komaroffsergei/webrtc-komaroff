# frozen_string_literal: true
#
require "logger"
require_relative "model_manager"
require_relative "../utils/audio_utils"
require_relative "transcriber"
require_relative "service"
require_relative "nats_client"
require_relative "rack_config"

module WhisperRuby
  module RackBootstrap
    RackState = Struct.new(:service, :thread, :boot_error, keyword_init: true) do
      def worker_state
        return "disabled" unless thread

        thread.alive? ? "running" : "stopped"
      end

      def service_running?
        service&.running?
      end

      def healthy?
        boot_error.nil?
      end

      def payload
        {
          status: healthy? ? "ok" : "error",
          worker: worker_state,
          service_running: service_running?,
          boot_error: boot_error&.message
        }
      end
    end

    module_function

    def state
      @state ||= RackState.new
    end

    def configure
      return state if defined?(RSpec)

      init_nats_client
      state.service = WhisperRuby::Service.new(config: RackConfig.build_service_config)
      state.thread = Thread.new { run_service(state) }
      at_exit do
        begin
          state.service&.stop
        rescue StandardError => e
          warn("Failed to stop WhisperRuby service: #{e}")
        end
      end
      state
    end

    def current_state(_context = nil)
      state
    end

    def init_nats_client
      $nats_client ||= NATSClient.new(RackConfig.nats_url)
    end

    def run_service(state)
      state.service.start
    rescue StandardError => e
      state.boot_error = e
      LOGGER.exception "Service stopped:", e
    end
  end
end

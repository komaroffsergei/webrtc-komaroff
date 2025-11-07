# frozen_string_literal: true

require "json"
require "logger"

require_relative "logging"

module WhisperRuby
  class Application
    HEALTH_OK = JSON.dump(status: "ok")

    def self.build(load_env: true, start_worker: service_enabled_by_default?)
      new(load_env: load_env, start_worker: start_worker)
    end

    def self.service_enabled_by_default?
      !%w[1 true yes on].include?(ENV.fetch("WHISPER_SERVICE_DISABLED", "0").downcase)
    end

    def initialize(load_env: true, start_worker: true)
      load_dotenv if load_env

      @config = ServiceConfig.from_env
      @logger = TaggedLogger.new($stdout)
      @logger.progname = @config.service_name
      @logger.level = log_level(@config.log_level)
      @service = nil
      @service_thread = nil
      @boot_error = nil

      start_service_thread if start_worker
    end

    def call(env)
      case env["PATH_INFO"]
      when "/healthcheck"
        serve_healthcheck
      else
        [404, {"Content-Type" => "application/json"}, [JSON.dump(error: "not_found")]]
      end
    end

    private

    def serve_healthcheck
      payload = {
        status: @boot_error ? "error" : "ok",
        worker: worker_state,
        service_running: @service&.running?,
        boot_error: @boot_error&.message
      }.compact

      status = payload[:status] == "ok" ? 200 : 503
      [status, {"Content-Type" => "application/json"}, [JSON.dump(payload)]]
    end

    def worker_state
      return "disabled" unless @service_thread
      return "running" if @service_thread.alive?

      "stopped"
    end

    def load_dotenv
      require "dotenv"
      Dotenv.load
    rescue LoadError
      # Dotenv is optional in production
    end

    def start_service_thread
      @service = Service.new(config: @config, logger: @logger)
      @service_thread = Thread.new do
        begin
          @service.start
        rescue StandardError => e
          @boot_error = e
          @logger.error("Service stopped: #{e}")
        end
      end
      @service_thread.report_on_exception = false
    end

    def log_level(level_name)
      Logger.const_get(level_name.upcase)
    rescue NameError
      Logger::INFO
    end
  end
end

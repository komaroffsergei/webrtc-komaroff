require "sinatra"
require "json"
require_relative "whisper_ruby/model_manager"
require_relative "utils/audio_utils"
require_relative "whisper_ruby/transcriber"
require_relative "whisper_ruby/service"
require_relative "whisper_ruby/nats_client"
require_relative "whisper_ruby/rack_config"

SERVICE_NAME = ENV["STACK_SERVICE_NAME"]
AUDIO_NATS_URL = ENV.fetch("NATS_URL")
NATS_WHISPER_SUBJECT = ENV.fetch("NATS_WHISPER_SUBJECT", "whisper.transcription")
NATS_LOGS_SUBJECT = ENV.fetch("NATS_LOGS_SUBJECT", "whisper.logs")


LOGGER.formatter = proc do |severity, datetime, progname, msg|
  timestamp = datetime.utc.iso8601(3)
  prog = progname ? "#{progname}: " : ""
  "[#{timestamp}] #{severity} #{prog}#{msg}\n"
end

StackServiceBase.rack_setup(self)

configure do |cong|
  cong.set nats_client = NATSClient.new(AUDIO_NATS_URL)
  cong.set service = WhisperRuby::Service.new(config: RackConfig.build_service_config)

  state.thread = Thread.new do
    state.service.start
  rescue StandardError => e
    state.boot_error = e
    LOGGER.exception "Service stopped:", e
  end

  at_exit do
    state.service&.stop
  rescue StandardError => e
    warn("Failed to stop WhisperRuby service: #{e}")
  end
end

get "/healthcheck" do
  thread.alive? ? "running" : "stopped"
  boot_error.nil?

  state = WhisperRuby::RackBootstrap.state
  content_type :json
  status(state.healthy? ? 200 : 503)
  state.payload.to_json
end

run Sinatra::Application

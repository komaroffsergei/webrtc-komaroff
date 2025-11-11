require "stack-service-base"
require "sinatra"
require "json"
require_relative "whisper_ruby/model_manager"
require_relative "utils/audio_utils"
require_relative "whisper_ruby/transcriber"
require_relative "whisper_ruby/service"
require_relative "whisper_ruby/nats_client"
require_relative "whisper_ruby/rack_config"

STATE = { service: nil, thread: nil, boot_error: nil }

StackServiceBase.rack_setup(self)

configure do
  config = WhisperRuby::RackConfig.build_service_config
  nats_client = NATSClient.new(config.nats.url, {}, service_name: config.service_name)
  STATE[:service] = WhisperRuby::Service.new(config:, nats_client:)
  STATE[:boot_error] = nil

  STATE[:thread] = Thread.new do
    STATE[:service].start
  rescue => e
    STATE[:boot_error] = e
    LOGGER.error("Service stopped: #{e.message}")
  end

  at_exit do
    STATE[:service]&.stop
    STATE[:thread]&.join(5)
  end
end

get "/healthcheck" do
  healthy = STATE[:boot_error].nil? && STATE[:service]&.running?
  content_type :json
  status(healthy ? 200 : 503)
  {
    status: healthy ? "ok" : "error",
    service: STATE[:service]&.config&.service_name,
    thread_alive: STATE[:thread]&.alive?,
    boot_error: STATE[:boot_error]&.message
  }.compact.to_json
end

run Sinatra::Application

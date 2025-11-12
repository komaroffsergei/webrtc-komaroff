require "stack-service-base"
require "sinatra"
require "json"
require_relative "whisper_ruby/model_manager"
require_relative "utils/audio_utils"
require_relative "whisper_ruby/transcriber"
require_relative "whisper_ruby/service"
require_relative "whisper_ruby/nats_client"
require_relative "whisper_ruby/rack_config"

StackServiceBase.rack_setup(self)

configure do
  config = WhisperRuby::RackConfig.build_service_config
  nats_client = NATSClient.new(config.nats.url, {}, service_name: config.service_name)
  set :service, WhisperRuby::Service.new(config:, nats_client:)
  set :boot_error, nil

  thread = Thread.new do
    settings.service.start
  rescue => e
    settings.boot_error = e
    LOGGER.error("Service stopped: #{e.message}")
  end
  set :thread, thread

  at_exit do
    settings.service&.stop
    settings.thread&.join(5)
  end
end unless defined? RSpec

get "/healthcheck" do
  healthy = settings.boot_error.nil? && settings.service&.running?
  content_type :json
  status(healthy ? 200 : 503)
  {
    Status: healthy ? "Healthy" : "unhealthy",
    service: settings.service&.config&.service_name,
    thread_alive: settings.thread&.alive?,
    boot_error: settings.boot_error&.message
  }.compact.to_json
end unless defined? RSpec

run Sinatra::Application

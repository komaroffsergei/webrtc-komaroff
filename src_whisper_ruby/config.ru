require "stack-service-base"
require "sinatra"
require "json"
require_relative "whisper_ruby/model_manager"
require_relative "utils/audio_utils"
require_relative "whisper_ruby/transcriber"
require_relative "whisper_ruby/service"
require_relative "whisper_ruby/nats_client"
require_relative "whisper_ruby/rack_config"

class ModelLoadStatuses
  LOADING = 'loading'
  LOADED = 'loaded'
  ERROR = 'error'
end

response = Rack::Response.new
STATE = { model_load_status: nil }

configure do
  config = WhisperRuby::RackConfig.build_service_config
  set :boot_error, nil



  # Preparing for downloading if necessary
  model_manager = WhisperRuby::ModelManager.new
  models_dir = config.whisper.models_dir
  asr_name   = config.whisper.model_name
  vad_name   = config.whisper.vad_model_name

  asr_path = model_manager.asr_target_path(models_dir:, model_name: asr_name)
  vad_path = model_manager.vad_target_path(models_dir:, vad_model_name: vad_name)
  # Decide and start background download if needed
  if File.file?(asr_path) && File.file?(vad_path)
    service.prepare_transcriber(model_path: asr_path, vad_model_path: vad_path)
    # settings.model_load_status = ModelLoadStatus::LOADED
    STATE[:model_load_status] = ModelLoadStatuses::LOADED
  else
    STATE[:model_load_status] = ModelLoadStatuses::LOADING
    # settings.model_load_status = ModelLoadStatus::LOADING
    Thread.new do
      begin
        sleep(10)
        # ensured_asr = File.file?(asr_path) ? asr_path : model_manager.ensure_asr(models_dir:, model_name: asr_name)
        # ensured_vad = File.file?(vad_path) ? vad_path : model_manager.ensure_vad(models_dir:, vad_model_name: vad_name)
        # service.prepare_transcriber(model_path: ensured_asr, vad_model_path: ensured_vad)
        # settings.model_load_status = ModelLoadStatus::LOADED
        STATE[:model_load_status] = ModelLoadStatuses::LOADED


      rescue => e
        # settings.model_load_status = ModelLoadStatus::ERROR
        STATE[:model_load_status] = ModelLoadStatuses::ERROR
        settings.boot_error = e
        LOGGER.error("Model preparation failed: #{e}")
      end
    end
  end








  nats_client = NATSClient.new(config.nats.url, {}, service_name: config.service_name)
  set :service, WhisperRuby::Service.new(config:, nats_client:)

  # set :model_load_status, ModelLoadStatus::LOADED

  # Immediately configure NATS logging, emit status and subscribe to NATS
  service = settings.service
  service.send(:configure_nats_logging)
  # set :latest_status, nil
  # status_sid = nats_client.loop_sub(config.nats.logs_subject) do |msg|
  #   begin
  #     data = JSON.parse(msg.data, symbolize_names: true)
  #     if data[:type] == "status"
  #       set :latest_status, data[:message]
  #     end
  #   rescue => e
  #     LOGGER.error("Failed to parse status log: #{e}")
  #   end
  # end


  thread = Thread.new do
    service.start
  rescue => e
    settings.boot_error = e
    LOGGER.error("Service stopped: #{e.message}")
  end
  set :thread, thread

  at_exit do
    settings.service&.stop
    settings.thread&.join(5)
    begin
      nats_client.unsubscribe(settings.status_subscription) if settings.respond_to?(:status_subscription) && settings.status_subscription
    rescue => e
      LOGGER.warn("Failed to unsubscribe status listener: #{e}")
    end
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

get "/rb_status" do
  content_type :json
  status(200)
  {
    model_status: settings.model_load_status,
    model_error: settings.boot_error&.message
  }.compact.to_json
end unless defined? RSpec

run Sinatra::Application

# frozen_string_literal: true

ENV['RUBYOPT'] = [ENV['RUBYOPT'], 'ruby-debug-ide'].compact.join(' ')

require "stack-service-base"
require "sinatra"

# ==== PATCH: override initialize_nats_service BEFORE it's called ====

def initialize_nats_service
  LOGGER.info "Initializing patched NATS service"

  nats_url = ENV["NATS_URL"].to_s
  raise "SWARM_NATS_URL is empty!" if nats_url.empty?

  $nats_client = NATS.connect(
    nats_url,
    max_reconnect_attempts: -1,
    reconnect_time_wait: 2
  )

  service = $nats_client.services.add(
    name: "#{ENV['STACK_SERVICE_NAME']}_#{ENV['STACK_NAME']}",
    version: "1.0.0",
    description: "patched service-base"
  )

  service.on_stop do
    LOGGER.info "Service stopped at #{Time.now}"
  end

  # Register endpoints WITHOUT self-tests
  service.endpoints.add("min") do |message|
    data = JSON.parse(message.data)
    message.respond(data.min.to_json)
  end

  service.endpoints.add("max") do |message|
    data = JSON.parse(message.data)
    message.respond(data.max.to_json)
  end

  LOGGER.info "NATS service initialized successfully"
end

# ==== END PATCH ====


require_relative "whisper_ruby/logger"
require_relative "whisper_ruby/model_downloader"
require_relative "whisper_ruby/phrase_packet"
require_relative "whisper_ruby/service"

StackServiceBase.rack_setup self

STACK_SERVICE_NAME=ENV["STACK_SERVICE_NAME"]
ASR_MODEL_URL = ENV["ASR_MODEL_URL"]
ASR_MODEL_SHA1 = ENV["ASR_MODEL_SHA1"]
ASR_MODELS = ENV["ASR_MODELS"]
MODEL_PATH = File.join(ASR_MODELS, File.basename(ASR_MODEL_URL))
NATS_LOGS_SUBJECT   = ENV["NATS_LOGS_SUBJECT"]
NATS_FRAMES_SUBJECT = ENV["NATS_FRAMES_SUBJECT"]
MIN_PHRASE_MS = 100


# Call your overridden initialize_nats_service
initialize_nats_service

Thread.new do
  service = WhisperRuby::Service.new(nc: $nats_client)
  service.run
rescue => e
  LOGGER.error "Whisper service crashed: #{e}"
end

get "/health" do
  content_type :json
  {status: "ok"}.to_json
end

run Sinatra::Application

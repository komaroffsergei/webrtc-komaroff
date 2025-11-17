# frozen_string_literal: true

require "stack-service-base"
require "sinatra"

require_relative "whisper_ruby/logger"
require_relative "whisper_ruby/model_downloader"
require_relative "whisper_ruby/phrase_packet"
require_relative "whisper_ruby/service"

StackServiceBase.rack_setup self

STACK_SERVICE_NAME=ENV["STACK_SERVICE_NAME"]
WHISPER_MODEL_URL = ENV["WHISPER_MODEL_URL"] # https://huggingface.co/ggerganov/whisper.cpp/tree/main
WHISPER_MODEL_SHA1 = ENV["WHISPER_MODEL_SHA1"] # https://huggingface.co/ggerganov/whisper.cpp
MODELS_DIR = ENV["MODELS_DIR"]
MODEL_PATH = File.join(MODELS_DIR, File.basename(WHISPER_MODEL_URL))
NATS_LOGS_SUBJECT   = ENV["NATS_LOGS_SUBJECT"]
NATS_FRAMES_SUBJECT = ENV["NATS_FRAMES_SUBJECT"]
MIN_PHRASE_MS = 100



# NATS init from stack-service-base
initialize_nats_service

# Start Whisper service in background
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

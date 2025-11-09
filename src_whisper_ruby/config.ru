require 'sinatra'
require 'ostruct'
require_relative "whisper_ruby/model_manager"
require_relative "whisper_ruby/phrase_packet"
require_relative "whisper_ruby/audio_utils"
require_relative "whisper_ruby/transcriber"
require_relative "whisper_ruby/service"
require_relative "whisper_ruby/nats_client"
require 'stack-service-base'

StackServiceBase.rack_setup self

SERVICE_NAME = ENV['STACK_SERVICE_NAME']

AUDIO_NATS_URL = ENV.fetch("NATS_URL", "nats://localhost:4222")
NATS_WHISPER_SUBJECT = (ENV["NATS_WHISPER_SUBJECT"] || "whisper.transcription").strip
NATS_LOGS_SUBJECT = (ENV["NATS_LOGS_SUBJECT"] || "whisper.logs").strip

unless defined? RSpec
  $nats_client = NATSClient.new AUDIO_NATS_URL
end

NATS_LOGGER = Class.new {
  def method_missing(name, d)

    $nats_client.publish NATS_LOGS_SUBJECT, {
      type: "log", level: level, category: category, message: message, service: SERVICE_NAME, timestamp: Time.now.utc.iso8601(3)
    }.merge(extra).compact.to_json

    LOGGER.send  name, "REST_API: #{d[:method]} #{d[:path]} #{d[:params]} - #{d[:status]} host:#{d[:host]} time:#{d[:time]}"
  end
}.new

def default_model_filename(name)
  base = name.dup
  base += ".bin" unless base.end_with?(".bin")
  base.start_with?("ggml-") ? base : "ggml-#{base}"
end

def default_vad_filename(name)
  return name if name&.end_with?(".bin")

  "ggml-#{name}.bin"
end

MODEL_FILENAME_HELPER = method(:default_model_filename)
VAD_FILENAME_HELPER = method(:default_vad_filename)

def truthy?(value)
  return false if value.nil?

  !%w[0 false no off].include?(value.to_s.strip.downcase)
end


configure do
  next if defined? RSpec

  threads = ENV.fetch("WHISPER_WORKERS", "1").to_i
  max_queue_default = [threads * 2, 4].max

  whisper_settings = {
    model_path: ENV["WHISPER_MODEL"],
    model_name: ENV["WHISPER_MODEL_NAME"] || "medium",
    model_url: ENV["WHISPER_MODEL_URL"],
    models_dir: ENV.fetch("WHISPER_MODELS_DIR", File.expand_path("../../models", __dir__)),
    language: ENV.fetch("WHISPER_LANGUAGE", "ru"),
    target_sample_rate: ENV.fetch("WHISPER_SAMPLE_RATE", "16000").to_i,
    worker_threads: threads,
    max_queue_size: ENV.fetch("WHISPER_MAX_QUEUE", max_queue_default).to_i,
    vad_model_path: ENV["WHISPER_VAD_MODEL_PATH"],
    vad_model_name: ENV["WHISPER_VAD_MODEL_NAME"] || "silero-v5.1.2",
    vad_threshold: ENV.fetch("WHISPER_VAD_THRESHOLD", "0.5").to_f,
    vad_min_speech_ms: ENV.fetch("WHISPER_VAD_MIN_SPEECH_MS", "250").to_i,
    vad_min_silence_ms: ENV.fetch("WHISPER_VAD_MIN_SILENCE_MS", "100").to_i,
    vad_max_speech_ms: ENV.fetch("WHISPER_VAD_MAX_SPEECH_MS", "#{30_000}").to_i,
    vad_speech_pad_ms: ENV.fetch("WHISPER_VAD_SPEECH_PAD_MS", "30").to_i,
    force_download: truthy?(ENV["WHISPER_FORCE_DOWNLOAD"]),
    translate: truthy?(ENV["WHISPER_TRANSLATE"]),
    n_threads: ENV.fetch("WHISPER_THREADS", Etc.nprocessors).to_i,
    temperature: ENV.fetch("WHISPER_TEMPERATURE", "0.0").to_i,
    temperature_inc: ENV.fetch("WHISPER_TEMPERATURE_INC", "0.2").to_f
  }

  whisper_config = OpenStruct.new(whisper_settings)
  whisper_config.define_singleton_method(:resolved_model_reference) do
    path = model_path.to_s.strip
    return path unless path.empty?

    base_dir = models_dir.to_s.strip
    base_dir = File.expand_path("../../models", __dir__) if base_dir.empty?

    filename = MODEL_FILENAME_HELPER.call((model_name || "medium").to_s)

    File.join(base_dir, filename)
  end
  whisper_config.define_singleton_method(:resolved_vad_reference) do
    path = vad_model_path.to_s.strip
    return path unless path.empty?

    base_dir = models_dir.to_s.strip
    base_dir = File.expand_path("../../models", __dir__) if base_dir.empty?

    filename = VAD_FILENAME_HELPER.call((vad_model_name || "silero-v5.1.2").to_s)

    File.join(base_dir, filename)
  end

  nats_config = OpenStruct.new(
    url: AUDIO_NATS_URL,
    whisper_subject: NATS_WHISPER_SUBJECT,
    logs_subject: NATS_LOGS_SUBJECT,
    connection_name: SERVICE_NAME || "src_whisper_ruby"
  )

  service_config = OpenStruct.new(
    service_name: SERVICE_NAME || "src_whisper_ruby",
    whisper: whisper_config,
    nats: nats_config
  )

  @service = WhisperRuby::Service.new config: service_config

  @service_thread = Thread.new do
    @service.start
  rescue StandardError => e
    @boot_error = e
    LOGGER.exception "Service stopped:", e
  end
end

get '/healthcheck' do
  content_type :json
  status @boot_error ? 503 : 200
  {
    status: @boot_error ? "error" : "ok",
    worker: worker_state,
    service_running: @service&.running?,
    boot_error: @boot_error&.message
  }.to_json
end

helpers do
  def worker_state
    return "disabled" unless @service_thread
    @service_thread.alive? ? "running" : "stopped"
  end
end

run Sinatra::Application

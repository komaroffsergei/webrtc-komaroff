# frozen_string_literal: true

require "ostruct"
require "etc"

module WhisperRuby
  module RackConfig
    module_function

    def build_whisper_config
      threads = ENV.fetch("WHISPER_WORKERS", "1").to_i
      max_queue_default = [threads * 2, 4].max

      settings = {
        model_path: ENV["WHISPER_MODEL"],
        model_name: ENV["WHISPER_MODEL_NAME"] || "medium",
        model_url: ENV["WHISPER_MODEL_URL"],
        models_dir: models_dir,
        language: ENV.fetch("WHISPER_LANGUAGE", "ru"),
        target_sample_rate: ENV.fetch("WHISPER_SAMPLE_RATE", "16000").to_i,
        worker_threads: threads,
        max_queue_size: ENV.fetch("WHISPER_MAX_QUEUE", max_queue_default).to_i,
        vad_model_path: ENV["WHISPER_VAD_MODEL_PATH"],
        vad_model_name: ENV["WHISPER_VAD_MODEL_NAME"] || "silero-v5.1.2",
        vad_threshold: ENV.fetch("WHISPER_VAD_THRESHOLD", "0.5").to_f,
        vad_min_speech_ms: ENV.fetch("WHISPER_VAD_MIN_SPEECH_MS", "250").to_i,
        vad_min_silence_ms: ENV.fetch("WHISPER_VAD_MIN_SILENCE_MS", "100").to_i,
        vad_max_speech_ms: ENV.fetch("WHISPER_VAD_MAX_SPEECH_MS", "30000").to_i,
        vad_speech_pad_ms: ENV.fetch("WHISPER_VAD_SPEECH_PAD_MS", "30").to_i,
        force_download: truthy?(ENV["WHISPER_FORCE_DOWNLOAD"]),
        translate: truthy?(ENV["WHISPER_TRANSLATE"]),
        n_threads: ENV.fetch("WHISPER_THREADS", Etc.nprocessors).to_i,
        temperature: ENV.fetch("WHISPER_TEMPERATURE", "0.2").to_f,
        temperature_inc: ENV.fetch("WHISPER_TEMPERATURE_INC", "0.2").to_f
      }

      config = OpenStruct.new(settings)
      config.define_singleton_method(:resolved_model_reference) do
        RackConfig.resolve_model_path(config)
      end
      config.define_singleton_method(:resolved_vad_reference) do
        RackConfig.resolve_vad_path(config)
      end
      config
    end

    def models_dir
      ENV.fetch("WHISPER_MODELS_DIR", File.expand_path("../../models", __dir__))
    end

    def resolve_model_path(config)
      path = config.model_path.to_s.strip
      return path unless path.empty?

      File.join(normalized_models_dir(config), default_model_filename(config.model_name || "medium"))
    end

    def resolve_vad_path(config)
      path = config.vad_model_path.to_s.strip
      return path unless path.empty?

      File.join(normalized_models_dir(config), default_vad_filename(config.vad_model_name || "silero-v5.1.2"))
    end

    def normalized_models_dir(config)
      dir = config.models_dir.to_s.strip
      return dir unless dir.empty?

      File.expand_path("../../models", __dir__)
    end

    def default_model_filename(name)
      base = name.to_s.dup
      base += ".bin" unless base.end_with?(".bin")
      base.start_with?("ggml-") ? base : "ggml-#{base}"
    end

    def default_vad_filename(name)
      value = name.to_s
      return value if value.end_with?(".bin")

      "ggml-#{value}.bin"
    end

    def env_string(key, fallback)
      (ENV[key] || fallback).strip
    end

    def truthy?(value)
      return false if value.nil?

      !%w[0 false no off].include?(value.to_s.strip.downcase)
    end
  end
end

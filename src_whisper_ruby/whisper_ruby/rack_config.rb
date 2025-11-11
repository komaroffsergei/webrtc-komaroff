# frozen_string_literal: true

require "ostruct"

module WhisperRuby
  module RackConfig
    module_function

    NATS_ENV = [
      [:url, "NATS_URL", :string],
      [:whisper_subject, "NATS_WHISPER_SUBJECT", :string],
      [:logs_subject, "NATS_LOGS_SUBJECT", :string]
    ].freeze

    WHISPER_ENV = [
      [:model_path, "WHISPER_MODEL", :string],
      [:model_name, "WHISPER_MODEL_NAME", :string],
      [:model_url, "WHISPER_MODEL_URL", :string],
      [:models_dir, "WHISPER_MODELS_DIR", :string],
      [:language, "WHISPER_LANGUAGE", :string],
      [:target_sample_rate, "WHISPER_SAMPLE_RATE", :integer],
      [:worker_threads, "WHISPER_WORKERS", :integer],
      [:max_queue_size, "WHISPER_MAX_QUEUE", :integer],
      [:vad_model_path, "WHISPER_VAD_MODEL_PATH", :string],
      [:vad_model_name, "WHISPER_VAD_MODEL_NAME", :string],
      [:vad_threshold, "WHISPER_VAD_THRESHOLD", :float],
      [:vad_min_speech_ms, "WHISPER_VAD_MIN_SPEECH_MS", :integer],
      [:vad_min_silence_ms, "WHISPER_VAD_MIN_SILENCE_MS", :integer],
      [:vad_max_speech_ms, "WHISPER_VAD_MAX_SPEECH_MS", :integer],
      [:vad_speech_pad_ms, "WHISPER_VAD_SPEECH_PAD_MS", :integer],
      [:force_download, "WHISPER_FORCE_DOWNLOAD", :boolean],
      [:translate, "WHISPER_TRANSLATE", :boolean],
      [:n_threads, "WHISPER_THREADS", :integer],
      [:temperature, "WHISPER_TEMPERATURE", :float],
      [:temperature_inc, "WHISPER_TEMPERATURE_INC", :float]
    ].freeze

    def build_service_config
      OpenStruct.new(
        service_name: env!("STACK_SERVICE_NAME"),
        nats: OpenStruct.new(load_values(NATS_ENV)),
        whisper: OpenStruct.new(load_values(WHISPER_ENV))
      )
    end

    def load_values(definitions)
      definitions.each_with_object({}) do |(attr, key, type), acc|
        acc[attr] = cast(env!(key), type)
      end
    end

    def env!(key)
      value = ENV.fetch(key) { raise KeyError, "Missing #{key}" }
      value.strip
    end

    def cast(value, type)
      case type
      when :integer then value.to_i
      when :float then value.to_f
      when :boolean then %w[1 true yes on].include?(value.downcase)
      else
        value
      end
    end
  end
end

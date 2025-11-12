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

    # Keep only minimal required whisper config and provide sane defaults.
    WHISPER_ENV = [
      [:model_name, "WHISPER_MODEL_NAME", :string, "medium"],
      [:vad_model_name, "WHISPER_VAD_MODEL_NAME", :string, "silero-v5.1.2"],
      [:models_dir, "WHISPER_MODELS_DIR", :string, "/app/models"],
      [:language, "WHISPER_LANGUAGE", :string, "ru"],
      [:target_sample_rate, "WHISPER_SAMPLE_RATE", :integer, 16000],
      [:worker_threads, "WHISPER_WORKERS", :integer, 2],
      [:max_queue_size, "WHISPER_MAX_QUEUE", :integer, 8],
      [:vad_threshold, "WHISPER_VAD_THRESHOLD", :float, 0.5],
      [:vad_min_speech_ms, "WHISPER_VAD_MIN_SPEECH_MS", :integer, 250],
      [:vad_min_silence_ms, "WHISPER_VAD_MIN_SILENCE_MS", :integer, 100],
      [:vad_max_speech_ms, "WHISPER_VAD_MAX_SPEECH_MS", :integer, 30000],
      [:vad_speech_pad_ms, "WHISPER_VAD_SPEECH_PAD_MS", :integer, 30],
      [:translate, "WHISPER_TRANSLATE", :boolean, false],
      [:n_threads, "WHISPER_THREADS", :integer, 4],
      [:temperature, "WHISPER_TEMPERATURE", :float, 0.2],
      [:temperature_inc, "WHISPER_TEMPERATURE_INC", :float, 0.2]
    ].freeze

    def build_service_config
      OpenStruct.new(
        service_name: service_name!,
        nats: OpenStruct.new(load_values(NATS_ENV)),
        whisper: OpenStruct.new(load_values(WHISPER_ENV))
      )
    end

    def load_values(definitions)
      definitions.each_with_object({}) do |(attr, key, type, default), acc|
        val = ENV.key?(key) ? ENV[key].to_s.strip : default
        acc[attr] = cast(val, type)
      end
    end

    def env!(key)
      value = ENV.fetch(key) { raise KeyError, "Missing #{key}" }
      value.strip
    end

    def service_name!
      (ENV["STACK_SERVICE_NAME"] || ENV["SERVICE_NAME"]).to_s.strip.tap do |val|
        raise KeyError, "Missing STACK_SERVICE_NAME or SERVICE_NAME" if val.empty?
      end
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

# frozen_string_literal: true

require "etc"

module WhisperRuby
  DEFAULT_SERVICE_NAME = "src_whisper_ruby"
  SERVICE_NAME_ALIASES = {
    "server" => "src_server",
    "webrtc-server" => "src_server",
    "src_server" => "src_server",
    "whisper" => "src_whisper",
    "src_whisper" => "src_whisper",
    "whisper_ruby" => "src_whisper_ruby",
    "src_whisper_ruby" => "src_whisper_ruby"
  }.freeze

  class ServiceConfig
    attr_reader :nats, :whisper, :log_level, :service_name

    def initialize(nats:, whisper:, log_level:, service_name:)
      @nats = nats
      @whisper = whisper
      @log_level = log_level
      @service_name = service_name
    end

    def self.from_env
      new(
        nats: NatsConfig.from_env,
        whisper: WhisperConfig.from_env,
        log_level: (ENV["LOG_LEVEL"] || "INFO").upcase,
        service_name: normalized_service_name(ENV["SERVICE_NAME"])
      )
    end

    def self.normalized_service_name(raw_name)
      key = raw_name.to_s.strip
      return DEFAULT_SERVICE_NAME if key.empty?

      mapped = SERVICE_NAME_ALIASES[key.downcase]
      mapped || DEFAULT_SERVICE_NAME
    end
  end

  class NatsConfig
    attr_reader :url, :whisper_subject, :logs_subject, :connection_name

    def initialize(url:, whisper_subject:, logs_subject:, connection_name:)
      @url = url
      @whisper_subject = whisper_subject
      @logs_subject = logs_subject
      @connection_name = connection_name
    end

    def self.from_env
      url = ENV.fetch("NATS_URL", "nats://localhost:4222")
      connection_name = ENV.fetch("NATS_CLIENT_NAME", DEFAULT_SERVICE_NAME)
      new(
        url: url,
        whisper_subject: resolve_subject(ENV["NATS_WHISPER_SUBJECT"], "whisper.transcription"),
        logs_subject: resolve_subject(ENV["NATS_LOGS_SUBJECT"], "whisper.logs"),
        connection_name: connection_name
      )
    end

    def self.resolve_subject(value, default)
      normalized = (value || "").strip
      normalized = default if normalized.empty?
      normalized.end_with?(".") ? normalized[0..-2] : normalized
    end
    private_class_method :resolve_subject
  end

  class WhisperConfig
    attr_reader :model_path,
                :model_name,
                :model_url,
                :models_dir,
                :language,
                :target_sample_rate,
                :worker_threads,
                :max_queue_size,
                :vad_model_path,
                :vad_model_name,
                :vad_threshold,
                :vad_min_speech_ms,
                :vad_min_silence_ms,
                :vad_max_speech_ms,
                :vad_speech_pad_ms,
                :force_download,
                :translate,
                :n_threads,
                :temperature,
                :temperature_inc

    def initialize(
      model_path:,
      model_name:,
      model_url:,
      models_dir:,
      language:,
      target_sample_rate:,
      worker_threads:,
      max_queue_size:,
      vad_model_path:,
      vad_model_name:,
      vad_threshold:,
      vad_min_speech_ms:,
      vad_min_silence_ms:,
      vad_max_speech_ms:,
      vad_speech_pad_ms:,
      force_download:,
      translate:,
      n_threads:,
      temperature:,
      temperature_inc:
    )
      @model_path = model_path
      @model_name = model_name
      @model_url = model_url
      @models_dir = models_dir
      @language = language
      @target_sample_rate = target_sample_rate
      @worker_threads = worker_threads
      @max_queue_size = max_queue_size
      @vad_model_path = vad_model_path
      @vad_model_name = vad_model_name
      @vad_threshold = vad_threshold
      @vad_min_speech_ms = vad_min_speech_ms
      @vad_min_silence_ms = vad_min_silence_ms
      @vad_max_speech_ms = vad_max_speech_ms
      @vad_speech_pad_ms = vad_speech_pad_ms
      @force_download = force_download
      @translate = translate
      @n_threads = n_threads
      @temperature = temperature
      @temperature_inc = temperature_inc
    end

    def self.from_env
      default_models_dir =
        if Dir.exist?("/app")
          "/app/models"
        else
          File.expand_path("../../models", __dir__)
        end

      workers = Integer(ENV.fetch("WHISPER_WORKERS", "1"))
      max_queue = Integer(ENV.fetch("WHISPER_MAX_QUEUE", [workers * 2, 4].max))

      new(
        model_path: string_or_nil(ENV["WHISPER_MODEL"]),
        model_name: string_or_nil(ENV["WHISPER_MODEL_NAME"]) || "medium",
        model_url: string_or_nil(ENV["WHISPER_MODEL_URL"]),
        models_dir: ENV.fetch("WHISPER_MODELS_DIR", default_models_dir),
        language: ENV.fetch("WHISPER_LANGUAGE", "ru"),
        target_sample_rate: Integer(ENV.fetch("WHISPER_SAMPLE_RATE", "16000")),
        worker_threads: workers,
        max_queue_size: max_queue,
        vad_model_path: string_or_nil(ENV["WHISPER_VAD_MODEL_PATH"]),
        vad_model_name: string_or_nil(ENV["WHISPER_VAD_MODEL_NAME"]) || "silero-v5.1.2",
        vad_threshold: Float(ENV.fetch("WHISPER_VAD_THRESHOLD", "0.5")),
        vad_min_speech_ms: Integer(ENV.fetch("WHISPER_VAD_MIN_SPEECH_MS", "250")),
        vad_min_silence_ms: Integer(ENV.fetch("WHISPER_VAD_MIN_SILENCE_MS", "100")),
        vad_max_speech_ms: Integer(ENV.fetch("WHISPER_VAD_MAX_SPEECH_MS", "#{30_000}")),
        vad_speech_pad_ms: Integer(ENV.fetch("WHISPER_VAD_SPEECH_PAD_MS", "30")),
        force_download: truthy?(ENV["WHISPER_FORCE_DOWNLOAD"]),
        translate: truthy?(ENV["WHISPER_TRANSLATE"]),
        n_threads: Integer(ENV.fetch("WHISPER_THREADS", Etc.nprocessors)),
        temperature: Float(ENV.fetch("WHISPER_TEMPERATURE", "0.0")),
        temperature_inc: Float(ENV.fetch("WHISPER_TEMPERATURE_INC", "0.2"))
      )
    end

    def resolved_model_reference
      return model_path if model_path && !model_path.empty?

      File.join(models_dir, default_model_filename(model_name))
    end

    def resolved_vad_reference
      return vad_model_path if vad_model_path && !vad_model_path.empty?

      File.join(models_dir, default_vad_filename(vad_model_name))
    end

    private

    def default_model_filename(name)
      base = name.dup
      base += ".bin" unless base.end_with?(".bin")
      base.start_with?("ggml-") ? base : "ggml-#{base}"
    end

    def default_vad_filename(name)
      return name if name&.end_with?(".bin")

      "ggml-#{name}.bin"
    end

    def self.string_or_nil(value)
      str = value&.strip
      str.nil? || str.empty? ? nil : str
    end
    private_class_method :string_or_nil

    def self.truthy?(value)
      return false if value.nil?

      !%w[0 false no off].include?(value.to_s.strip.downcase)
    end
    private_class_method :truthy?
  end
end

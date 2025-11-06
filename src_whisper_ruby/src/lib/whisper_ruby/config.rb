# frozen_string_literal: true

require "ostruct"

module WhisperRuby
  module Config
    module_function

    def resolve_subject(value, default)
      subject = value.to_s.strip
      subject = default if subject.empty?
      subject.end_with?(".") ? subject[0..-2] : subject
    end

    def nats
      OpenStruct.new(
        url: ENV.fetch("NATS_URL", "nats://localhost:4222"),
        audio_subject: resolve_subject(ENV["NATS_AUDIO_SUBJECT"], "audio.frames"),
        whisper_subject: resolve_subject(ENV["NATS_WHISPER_SUBJECT"], "whisper.transcription"),
        logs_subject: resolve_subject(ENV["NATS_LOGS_SUBJECT"], "whisper.logs")
      )
    end

    def whisper
      OpenStruct.new(
        model_path: ENV.fetch(
          "WHISPER_MODEL",
          File.expand_path("../../models/whisper-medium-ru-fine-ct2/model.bin", __dir__)
        ),
        model_ggml_path: ENV.fetch(
          "WHISPER_GGML_MODEL",
          File.expand_path("../../models/ggml-small.bin", __dir__)
        ),
        recordings_dir: ENV.fetch("RECORDINGS_DIR", File.expand_path("../../recordings", __dir__)),
        save_recordings: ENV.fetch("SAVE_RECORDINGS", "true").downcase == "true",
        target_sample_rate: Integer(ENV.fetch("TARGET_SAMPLE_RATE", "16000")),
        device: ENV.fetch("WHISPER_DEVICE", "cpu"),
        compute_type: ENV.fetch("WHISPER_COMPUTE_TYPE", "int8"),
        language: ENV.fetch("WHISPER_LANGUAGE", "ru")
      )
    end

    def service
      OpenStruct.new(
        log_level: ENV.fetch("LOG_LEVEL", "INFO"),
        worker_threads: Integer(ENV.fetch("WORKER_THREADS", "2")),
        request_timeout: Float(ENV.fetch("REQUEST_TIMEOUT", "15.0"))
      )
    end
  end
end

# frozen_string_literal: true

require "json"
require "time"

module WhisperRuby
  class NatsLogger
    LEVELS = %w[debug info warning error].freeze

    def initialize(nats_client, subject:, service_name:)
      @nats = nats_client
      @subject = subject
      @service_name = service_name
    end

    def log(level, message, category: "general", **extra)
      return unless connected?

      payload = {
        type: "log",
        level: normalize_level(level),
        category: category,
        message: message,
        service: @service_name,
        timestamp: Time.now.utc.iso8601
      }
      payload.merge!(extra) unless extra.empty?

      publish(payload)
    end

    def log_debug(message, **extra)
      log("debug", message, **extra)
    end

    def log_info(message, **extra)
      log("info", message, **extra)
    end

    def log_warning(message, **extra)
      log("warning", message, **extra)
    end

    def log_error(message, **extra)
      log("error", message, **extra)
    end

    def log_transcription(text:, segments:, audio_duration:, transcription_time:, start_timestamp:, end_timestamp:)
      rtf = audio_duration.positive? ? (transcription_time / audio_duration) : 0.0
      log_info(
        "Transcription completed: audio_duration=#{format('%.2f', audio_duration)}s transcription_time=#{format('%.2f', transcription_time)}s segments=#{segments} start=#{start_timestamp} end=#{end_timestamp}",
        category: "whisper",
        text: text,
        segments: segments,
        audio_duration: audio_duration,
        transcription_time: transcription_time,
        rtf: rtf.round(2),
        start: start_timestamp,
        end: end_timestamp
      )
    end

    def log_transcription_start(audio_duration:, audio_bytes:)
      start_timestamp = Time.now.utc.iso8601
      log_info(
        "Transcription started: audio_duration=#{format('%.2f', audio_duration)}s bytes=#{audio_bytes}",
        category: "whisper",
        audio_duration: audio_duration,
        audio_bytes: audio_bytes,
        start: start_timestamp
      )
      start_timestamp
    end

    def log_event(event_type:, message:, category: "system", level: "info", **extra)
      log(level, message, category: category, event_type: event_type, **extra)
    end

    private

    def connected?
      @nats && @nats.connected?
    rescue StandardError
      false
    end

    def normalize_level(level)
      value = level.to_s.downcase
      LEVELS.include?(value) ? value : "info"
    end

    def publish(payload)
      @nats.publish(@subject, JSON.dump(payload))
    rescue StandardError => e
      warn "[whisper.nats_logger] failed to publish log: #{e}"
    end
  end
end

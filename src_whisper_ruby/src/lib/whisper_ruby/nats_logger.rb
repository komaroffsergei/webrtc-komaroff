# frozen_string_literal: true

require "json"
require "time"

require_relative "logging"

module WhisperRuby
  class NatsLogger
    def initialize(nats_client, subject:, service_name:)
      @nats = nats_client
      @subject = subject
      @service_name = service_name
      @mutex = Mutex.new
    end

    def log_info(message, category: "general", **extra)
      publish("info", message, category: category, extra: extra)
    end

    def log_warning(message, category: "general", **extra)
      publish("warning", message, category: category, extra: extra)
    end

    def log_error(message, category: "general", **extra)
      publish("error", message, category: category, extra: extra)
    end

    def log_transcription(text:, segments:, audio_duration:, transcription_time:, start_timestamp:, end_timestamp:)
      rtf = if audio_duration.to_f.positive? && transcription_time.to_f.positive?
              transcription_time.to_f / audio_duration.to_f
            else
              0.0
            end

      extra = {
        text: text,
        segments: segments,
        audio_duration: audio_duration,
        transcription_time: transcription_time,
        rtf: rtf.round(2),
        start: start_timestamp,
        end: end_timestamp
      }
      publish(
        "info",
        "Transcription completed: audio=#{audio_duration.round(2)}s text=#{text}s time=#{transcription_time.round(2)}s segments=#{segments}",
        category: "whisper",
        extra: extra
      )
    end

    private

    def publish(level, message, category:, extra:)
      return unless @nats && @nats.connected?

      tagged_message = LogTag.apply(message)

      payload = {
        type: "log",
        level: level,
        category: category,
        message: tagged_message,
        service: @service_name,
        timestamp: Time.now.utc.iso8601(3)
      }
      payload.merge!(extra.compact) if extra && !extra.empty?

      data = JSON.generate(payload)
      @mutex.synchronize do
        @nats.publish(@subject, data)
      end
    rescue StandardError => e
      warn("Failed to publish log to NATS: #{e}")
    end
  end
end

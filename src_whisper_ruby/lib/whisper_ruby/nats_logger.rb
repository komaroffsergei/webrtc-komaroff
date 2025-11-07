# frozen_string_literal: true

require "json"
require "time"

require_relative "logging"

module WhisperRuby
  class NatsLogger
    def initialize(nats_client, subject:, service_name:)
      @nats = nats_client
      @subject = subject
      @service_name = service_name.to_s.strip.empty? ? DEFAULT_SERVICE_NAME : service_name
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

    def log_event(event:, message:, category: "system", level: "info", **extra)
      extra[:event] = event
      publish(level, message, category: category, extra: extra)
    end

    def log_transcription_start(audio_duration:, audio_samples:, sample_rate:, phrase_id: nil, start_timestamp: nil, metadata: nil)
      ts = start_timestamp || Time.now.utc.iso8601(3)
      extra = {
        audio_duration: audio_duration,
        audio_samples: audio_samples,
        sample_rate: sample_rate,
        start: ts,
        event: "transcription_started"
      }
      extra[:phrase_id] = phrase_id if phrase_id
      extra[:metadata] = metadata if metadata

      message = format(
        "Transcription started: audio=%.2fs samples=%d sample_rate=%d",
        audio_duration.to_f,
        audio_samples.to_i,
        sample_rate.to_i
      )
      publish("info", message, category: "whisper", extra: extra)
      ts
    end

    def log_transcription(text:, segments:, audio_duration:, transcription_time:, start_timestamp:, end_timestamp:, phrase_id: nil, event: "transcription_completed")
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
        end: end_timestamp,
        event: event
      }
      extra[:phrase_id] = phrase_id if phrase_id
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

      payload = {
        type: "log",
        level: level,
        category: category,
        message: message,
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

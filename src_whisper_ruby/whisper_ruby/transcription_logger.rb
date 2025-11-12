# frozen_string_literal: true

module WhisperRuby
  class TranscriptionLogger
    def initialize(nats_client:)
      @nats_client = nats_client
      @enabled = false
    end

    def configure(subject:)
      return unless @nats_client.respond_to?(:configure_logging)

      @nats_client.configure_logging(subject: subject)
      @enabled = true
    end

    def enabled? = @enabled

    # Public helper to send status updates (e.g., downloading/ready)
    def log_status(value)
      publish(message: value.to_s, type: "status")
    end

    def phrase_received(packet)
      return unless active?(packet)

      publish(
        message: format(
          "Phrase %s received samples=%d sr=%dHz duration=%.2fs",
          packet.phrase_id || "unknown",
          packet.audio.length,
          packet.sample_rate,
          packet.duration
        )
      )
    end

    def transcription_start(packet, start_ts)
      return unless active?(packet)

      publish(
        message: format(
          "Transcription started for %s duration=%.2fs start=%s",
          packet.phrase_id || "unknown",
          packet.duration,
          start_ts
        )
      )
    end

    def transcription_complete(packet, result, start_ts, end_ts)
      return if result.text.to_s.empty?
      return unless enabled?

      publish(
        message: format(
          "Transcription completed for %s segments=%d audio=%.2fs time=%.2fs %s->%s text=\"%s\"",
          packet.phrase_id || "unknown",
          result.segments.length,
          result.audio_duration,
          result.transcription_time,
          start_ts,
          end_ts,
          shorten_text(result.text)
        )
      )
    end

    def transcription_error(event, error, packet:, extra: nil)
      details = [
        "#{event}",
        "#{error.class}: #{error.message}"
      ]
      if packet
        details << "phrase_id=#{packet.phrase_id}" if packet.phrase_id
        details << "sr=#{packet.sample_rate}"
        details << format("duration=%.2fs", packet.duration) if packet.duration
      end
      details << extra.inspect if extra

      publish(
        message: "#{details.compact.join(' ')} | #{Array(error.backtrace).join(' >> ')}",
        type: "error"
      )
    end

    def shutdown = @enabled = false

    private

    def active?(packet) = enabled? && packet

    def publish(message:, type: "info")
      return unless enabled?
      @nats_client.log(message:, type:)
    end

    def shorten_text(text)
      normalized = text.to_s.strip.gsub(/\s+/, ' ')
      return normalized if normalized.length <= 120

      "#{normalized[0, 117]}..."
    end
  end
end

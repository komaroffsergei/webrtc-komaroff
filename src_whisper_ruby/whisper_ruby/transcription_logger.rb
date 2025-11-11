# frozen_string_literal: true

module WhisperRuby
  class TranscriptionLogger
    def initialize(nats_client:)
      @nats_client = nats_client
      @enabled = false
    end

    def configure(subject:)
      return unless @nats_client.respond_to?(:configure_logging)

      @nats_client.configure_logging(subject: subject, service_name: ENV['STACK_SERVICE_NAME'] || 'undefined_service' )
      @enabled = true
    rescue StandardError => e
      LOGGER.warn("Failed to configure NATS logging: #{e}")
      @enabled = false
    end

    def enabled?
      @enabled
    end

    def phrase_received(packet)
      return unless packet
      message = format(
        "Phrase %s received (%d samples @ %dHz, duration %.2fs)",
        packet.phrase_id || "unknown",
        packet.audio.length,
        packet.sample_rate,
        packet.duration
      )
      LOGGER.info(message)

      return unless enabled?

      deliver(:event, {
        event: "phrase_received",
        message: message,
        category: "transcription",
        phrase_id: packet.phrase_id,
        sample_rate: packet.sample_rate,
        audio_duration: packet.duration.round(3),
        audio_samples: packet.audio.length,
        metadata: packet.metadata
      })
    end

    def transcription_start(packet, start_ts)
      return unless packet
      message = format(
        "Transcription started for %s (duration %.2fs)",
        packet.phrase_id || "unknown",
        packet.duration
      )
      LOGGER.info(message)

      return unless enabled?

      deliver(:transcription_start, {
        audio_duration: packet.duration,
        audio_samples: packet.audio.length,
        sample_rate: packet.sample_rate,
        phrase_id: packet.phrase_id,
        start_timestamp: start_ts,
        metadata: packet.metadata
      })
    end

    def transcription_complete(packet, result, start_ts, end_ts)
      return if result.text.to_s.empty?

      message = format(
        "Transcription completed for %s (segments=%d, duration %.2fs)",
        packet.phrase_id || "unknown",
        result.segments.length,
        packet.duration
      )
      LOGGER.info(message)

      return unless enabled?

      deliver(:transcription, {
        text: result.text,
        segments: result.segments.length,
        audio_duration: result.audio_duration,
        transcription_time: result.transcription_time,
        start_timestamp: start_ts,
        end_timestamp: end_ts,
        phrase_id: packet.phrase_id
      })
    end

    def transcription_error(event, error, packet:, extra: nil)
      payload = {
        event: event,
        error_type: error.class.name,
        error_message: error.message,
        stacktrace: Array(error.backtrace).join("\n")
      }
      if packet
        payload[:phrase_id] = packet.phrase_id if packet.phrase_id
        payload[:sample_rate] = packet.sample_rate
        payload[:audio_duration] = packet.duration
        payload[:metadata] = packet.metadata
      end
      payload.merge!(extra) if extra

      error_message = "#{event}: #{error.message}"
      LOGGER.error(error_message)

      return unless enabled?

      deliver(:error, {
        message: error_message,
        category: "whisper",
        extra: payload
      })
    end

    def shutdown
      @enabled = false
    end

    private

    def deliver(action, payload)
      dispatch_log(action, payload)
    rescue StandardError => e
      LOGGER.warn("Failed to dispatch log action #{action}: #{e}")
    end

    def dispatch_log(action, payload)
      case action
      when :transcription
        @nats_client.log_transcription(**payload)
      when :transcription_start
        @nats_client.log_transcription_start(**payload)
      when :event
        @nats_client.log_event(**payload)
      when :error
        extra = payload.fetch(:extra, {})
        @nats_client.log_error(payload.fetch(:message), category: payload.fetch(:category, "general"), **extra)
      else
        LOGGER.debug("Unhandled log action: #{action}")
      end
    end
  end
end

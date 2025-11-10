# frozen_string_literal: true

require "thread"

module WhisperRuby
  class TranscriptionLogger
    DEFAULT_QUEUE_SIZE = 128
    STOP_TOKEN = :stop

    def initialize(nats_client:, queue_size: DEFAULT_QUEUE_SIZE)
      @nats_client = nats_client
      @queue = SizedQueue.new(queue_size)
      @worker = nil
      @enabled = false
    end

    def configure(subject:, service_name:)
      return unless @nats_client.respond_to?(:configure_logging)

      @nats_client.configure_logging(subject: subject, service_name: service_name)
      @enabled = true
      start_worker
    rescue StandardError => e
      LOGGER.warn("Failed to configure NATS logging: #{e}")
      @enabled = false
    end

    def enabled?
      @enabled
    end

    def phrase_received(packet)
      return unless enabled? && packet

      log_async(:event, {
        event: "phrase_received",
        message: "Phrase received from NATS",
        category: "transcription",
        phrase_id: packet.phrase_id,
        sample_rate: packet.sample_rate,
        audio_duration: packet.duration.round(3),
        audio_samples: packet.audio.length,
        metadata: packet.metadata
      })
    end

    def transcription_start(packet, start_ts)
      return unless enabled? && packet

      log_async(:transcription_start, {
        audio_duration: packet.duration,
        audio_samples: packet.audio.length,
        sample_rate: packet.sample_rate,
        phrase_id: packet.phrase_id,
        start_timestamp: start_ts,
        metadata: packet.metadata
      })
    end

    def transcription_complete(packet, result, start_ts, end_ts)
      return unless enabled?
      return if result.text.to_s.empty?

      log_async(:transcription, {
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
      return unless enabled?

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

      log_async(:error, {
        message: "#{event}: #{error.message}",
        category: "whisper",
        extra: payload
      })
    end

    def shutdown
      return unless @worker

      push([STOP_TOKEN, nil])
      @worker.join(1)
    rescue StandardError => e
      LOGGER.warn("Failed to stop log worker: #{e}")
    ensure
      @worker = nil
    end

    private

    def start_worker
      return @worker if @worker&.alive?

      @worker = Thread.new do
        loop do
          action, payload = @queue.pop
          break if action == STOP_TOKEN
          dispatch_log(action, payload)
        rescue StandardError => e
          LOGGER.warn("Log worker error: #{e}")
        end
      end.tap { |thr| thr.report_on_exception = false }
    end

    def log_async(action, payload)
      start_worker
      push([action, payload])
    end

    def push(payload)
      @queue.push(payload, true)
    rescue ThreadError
      begin
        @queue.pop(true)
      rescue ThreadError
        sleep 0.01
      end
      retry
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

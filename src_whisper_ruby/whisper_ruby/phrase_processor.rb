# frozen_string_literal: true

require "json"
require "time"

module WhisperRuby
  class PhraseProcessor
    def initialize(transcriber:, logger:, config:, nats_client:)
      @transcriber = transcriber
      @logger = logger
      @config = config
      @nats_client = nats_client
    end

    def process(msg)
      packet = nil
      packet = PhrasePacket.from_bytes(msg.data)
      @logger.phrase_received(packet)
      start_ts = timestamp_now
      @logger.transcription_start(packet, start_ts)
      result = @transcriber.transcribe(packet)
      end_ts = timestamp_now

      payload = build_payload(packet, result, start_ts, end_ts)
      @logger.transcription_complete(packet, result, start_ts, end_ts)
      reply(msg, payload)
      LOGGER.info("Transcription done for #{packet.phrase_id || 'unknown'}")
    rescue PhrasePacketError => e
      LOGGER.error("Failed to parse phrase: #{e}")
      @logger.transcription_error(
        "phrase_parse_failed",
        e,
        packet: nil,
        extra: {payload_size: msg.data&.bytesize}
      )
      reply_with_error(msg, e.message)
    rescue StandardError => e
      LOGGER.error("Transcription failed: #{e}")
      @logger.transcription_error("transcription_failed", e, packet: packet)
      reply_with_error(msg, e.message, packet&.phrase_id)
    end

    private

    def build_payload(packet, result, start_ts, end_ts)
      {
        type: "transcription",
        service: @config.service_name,
        timestamp: end_ts,
        phrase_id: packet.phrase_id,
        text: result.text,
        segments: result.segments.length,
        audio_duration: result.audio_duration,
        transcription_time: result.transcription_time,
        start_timestamp: start_ts,
        end_timestamp: end_ts
      }
    end

    def reply(msg, payload)
      data = JSON.generate(ensure_utf8(payload))
      destination = msg.reply && !msg.reply.empty? ? msg.reply : "#{@config.nats.whisper_subject}.result"
      publish(destination, data)
    end

    def reply_with_error(msg, error, phrase_id = nil)
      reply(
        msg,
        {
          type: "transcription",
          error: error,
          phrase_id: phrase_id
        }
      )
    end

    def publish(subject, data)
      @nats_client.publish(subject, data)
    end

    def ensure_utf8(value)
      case value
      when String
        str = value.dup
        str = str.force_encoding(Encoding::UTF_8)
        str.encode!(Encoding::UTF_8, invalid: :replace, undef: :replace)
        str
      when Hash
        value.transform_values { |v| ensure_utf8(v) }
      when Array
        value.map { |v| ensure_utf8(v) }
      else
        value
      end
    end

    def timestamp_now
      Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%L")
    end
  end
end

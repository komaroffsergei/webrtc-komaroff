# frozen_string_literal: true

require "json"
require "time"

require_relative "../utils/audio_utils"
require_relative "../utils/text_utils"
require_relative "../utils/transcription_response"

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
      packet = AudioUtils.parse_phrase_packet(msg.data)
      @logger.phrase_received(packet)
      start_ts = timestamp_now
      @logger.transcription_start(packet, start_ts)
      result = @transcriber.transcribe(packet)
      end_ts = timestamp_now

      payload = TranscriptionResponse.success(
        config: @config,
        packet: packet,
        result: result,
        start_ts: start_ts,
        end_ts: end_ts
      )
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

    def reply(msg, payload)
      data = JSON.generate(TextUtils.ensure_utf8(payload))
      destination = msg.reply && !msg.reply.empty? ? msg.reply : "#{@config.nats.whisper_subject}.result"
      @nats_client.publish(destination, data)
    end

    def reply_with_error(msg, error, phrase_id = nil)
      payload = TranscriptionResponse.error(error: error, phrase_id: phrase_id)
      reply(msg, payload)
    end

    def timestamp_now
      Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%L")
    end
  end
end

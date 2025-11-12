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
      @logger.log_status(STATE[:model_load_status])
    end

    def process(msg)
      LOGGER.info("Processing message subject=#{msg.subject} reply=#{msg.reply} size=#{msg.data&.bytesize}")
      packet = nil
      packet = AudioUtils.parse_phrase_packet(msg.data)
      LOGGER.info(
        "Packet parsed phrase_id=#{phrase_id(packet)} sample_rate=#{packet.sample_rate} samples=#{packet.audio.length} duration=#{format('%.3f', packet.duration)}"
      )
      @logger.phrase_received(packet)
      start_ts = timestamp_now
      @logger.transcription_start(packet, start_ts)
      LOGGER.info("Starting transcription phrase_id=#{phrase_id(packet)} thread=#{Thread.current.name || Thread.current.object_id}")
      transcribe_started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
      result = @transcriber.transcribe(packet)
      transcription_duration = Process.clock_gettime(Process::CLOCK_MONOTONIC) - transcribe_started
      LOGGER.info(
        "Transcription finished phrase_id=#{phrase_id(packet)} segments=#{result.segments.length} text_length=#{result.text.to_s.length} time=#{format('%.3f', transcription_duration)}s"
      )
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
      LOGGER.info("Transcription done phrase_id=#{phrase_id(packet)}")
    rescue PhrasePacketError => e
      log_and_report_error("phrase_parse_failed", e, packet: nil, extra: {payload_size: msg.data&.bytesize})
      reply_with_error(msg, e.message)
    rescue StandardError => e
      log_and_report_error("transcription_failed", e, packet: packet)
      reply_with_error(msg, e.message, packet&.phrase_id)
    rescue Exception => e
      LOGGER.fatal("Unexpected fatal error phrase_id=#{phrase_id(packet)}: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
      raise
    end

    private

    def reply(msg, payload)
      data = JSON.generate(TextUtils.ensure_utf8(payload))
      destination = msg.reply && !msg.reply.empty? ? msg.reply : "#{@config.nats.whisper_subject}.result"
      @nats_client.publish(destination, data)
      LOGGER.info("Published response phrase_id=#{payload[:phrase_id]} destination=#{destination} size=#{data.bytesize}")
    end

    def reply_with_error(msg, error, phrase_id = nil)
      payload = TranscriptionResponse.error(error: error, phrase_id: phrase_id)
      reply(msg, payload)
    end

    def log_and_report_error(event, error, packet:, extra: nil)
      LOGGER.error("#{event} phrase_id=#{phrase_id(packet)} error=#{error.class}: #{error.message}\n#{error.full_message}")
      @logger.transcription_error(event, error, packet: packet, extra: extra)
    end

    def timestamp_now
      Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%L")
    end

    def phrase_id(packet)
      packet&.phrase_id || "unknown"
    end
  end
end

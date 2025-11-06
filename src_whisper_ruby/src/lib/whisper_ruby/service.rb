# frozen_string_literal: true

require "concurrent-ruby"
require "fileutils"
require "json"
require "logger"
require "time"
require "nats/io/client"
require "ostruct"

require_relative "config"
require_relative "phrase_packet"
require_relative "transcriber"
require_relative "nats_logger"

module WhisperRuby
  class Service
    DEFAULT_SUBJECT_SUFFIX = ".result"

    def initialize(config: Config, logger: nil)
      @config = OpenStruct.new(
        nats: config.nats,
        whisper: config.whisper,
        service: config.service
      )
      @logger = logger || build_logger(@config.service.log_level)
      @executor = build_executor(@config.service.worker_threads)
      @nats = nil
      @nats_logger = nil
      @transcriber = nil
      @subscription = nil
      @started = false
      @shutdown = false
    end

    def start
      return if @started

      connect_nats
      setup_logging
      start_transcriber
      subscribe

      @started = true
      @logger.info("WhisperRuby service started, listening on #{@config.nats.whisper_subject}")
      @nats_logger&.log_info(
        "WhisperRuby service started",
        category: "whisper",
        subject: @config.nats.whisper_subject
      )
    rescue StandardError => e
      @logger.error("Failed to start service: #{e}")
      raise
    end

    def stop
      return if @shutdown

      @shutdown = true
      @nats&.drain_sub(@subscription) if @subscription
      @executor.shutdown
      @executor.wait_for_termination(5)
      @transcriber&.shutdown
      @nats&.close
    rescue StandardError => e
      @logger.warn("Error during shutdown: #{e}")
    end

    private

    def build_logger(level)
      logger = Logger.new($stdout)
      logger.level = case level.to_s.upcase
                     when "DEBUG" then Logger::DEBUG
                     when "INFO" then Logger::INFO
                     when "WARNING", "WARN" then Logger::WARN
                     when "ERROR" then Logger::ERROR
                     else Logger::INFO
                     end
      logger.progname = "whisper_ruby"
      logger
    end

    def build_executor(size)
      max_threads = [size, 1].max
      Concurrent::ThreadPoolExecutor.new(
        min_threads: 1,
        max_threads: max_threads,
        max_queue: max_threads * 4,
        fallback_policy: :caller_runs
      )
    end

    def connect_nats
      urls = @config.nats.url.to_s.split(",").map(&:strip).reject(&:empty?)
      @nats = NATS::Client.new
      @nats.connect(
        servers: urls.empty? ? [NATS::Client::DEFAULT_URI] : urls,
        reconnect: true,
        max_reconnect_attempts: -1,
        reconnect_time_wait: 2,
        ping_interval: 10
      )

      @logger.info("Connected to NATS: #{@nats.server_info[:client_id]} #{@nats.uri}")
    end

    def setup_logging
      return unless @nats

      @nats_logger = NatsLogger.new(@nats, subject: @config.nats.logs_subject, service_name: "whisper_ruby")

      @nats.on_error do |error|
        @logger.error("NATS error: #{error}")
        @nats_logger&.log_error("NATS error: #{error}", category: "nats")
      end

      @nats.on_disconnect do
        @logger.warn("Disconnected from NATS")
        @nats_logger&.log_warning("Disconnected from NATS", category: "nats")
      end

      @nats.on_reconnect do
        @logger.info("Reconnected to NATS: #{@nats.uri}")
        @nats_logger&.log_info("Reconnected to NATS", category: "nats", uri: @nats.uri.to_s)
      end
    end

    def start_transcriber
      @transcriber ||= Transcriber.new(config: @config.whisper, logger: @logger)
    end

    def subscribe
      @subscription = @nats.subscribe(@config.nats.whisper_subject) do |msg|
        @executor.post do
          handle_message(msg)
        rescue StandardError => e
          @logger.error("Message handling failed: #{e}")
          @nats_logger&.log_error("Message handling failed: #{e}", category: "system")
        end
      end
    end

    def handle_message(msg)
      packet = nil
      packet = PhrasePacket.from_bytes(msg.data)
      maybe_store_recording(packet)

      result = process_transcription(packet)
      respond(msg, result)
    rescue PhrasePacketError => e
      respond(msg, error_payload(e.message, nil))
      @logger.error("Failed to parse phrase: #{e.message}")
      @nats_logger&.log_error("Failed to parse phrase", category: "whisper", error: e.message)
    rescue Transcriber::Error => e
      respond(msg, error_payload(e.message, packet&.phrase_id))
      @logger.error("Transcription error: #{e.message}")
      @nats_logger&.log_error("Transcription error", category: "whisper", error: e.message)
    rescue StandardError => e
      respond(msg, error_payload(e.message, packet&.phrase_id))
      @logger.error("Unexpected error: #{e}")
      @nats_logger&.log_error("Unexpected transcription error", category: "whisper", error: e.message)
    end

    def process_transcription(packet)
      start_ts = Time.now.utc.iso8601

      result = @transcriber.transcribe(packet, timeout: @config.service.request_timeout)
      end_ts = result["end_timestamp"] || Time.now.utc.iso8601
      payload = {
        "type" => "transcription",
        "phrase_id" => packet.phrase_id,
        "text" => result["text"],
        "segments" => result["segments"].to_i,
        "audio_duration" => result["audio_duration"].to_f,
        "transcription_time" => result["transcription_time"].to_f,
        "start_timestamp" => result["start_timestamp"] || start_ts,
        "end_timestamp" => end_ts
      }

      if payload["text"] && !payload["text"].empty?
        @nats_logger&.log_transcription(
          text: payload["text"],
          segments: payload["segments"],
          audio_duration: payload["audio_duration"],
          transcription_time: payload["transcription_time"],
          start_timestamp: payload["start_timestamp"],
          end_timestamp: payload["end_timestamp"]
        )
      end

      payload
    end

    def respond(msg, payload)
      body = JSON.dump(payload)
      if msg.reply && !msg.reply.empty?
        msg.respond(body)
      else
        @nats.publish(@config.nats.whisper_subject + DEFAULT_SUBJECT_SUFFIX, body)
      end
    rescue StandardError => e
      @logger.error("Failed to respond: #{e}")
      @nats_logger&.log_error("Failed to respond", category: "whisper", error: e.message)
    end

    def error_payload(message, phrase_id)
      {
        "type" => "transcription",
        "error" => message,
        "phrase_id" => phrase_id
      }
    end

    def maybe_store_recording(packet)
      return unless @config.whisper.save_recordings

      dir = @config.whisper.recordings_dir
      FileUtils.mkdir_p(dir)
      base = packet.phrase_id || "phrase_#{Time.now.utc.strftime('%Y%m%dT%H%M%S')}"
      safe_name = base.gsub(/[^0-9A-Za-z_\-]/, "_")
      path = File.join(dir, "#{safe_name}.raw")
      File.binwrite(path, packet.raw_audio)
    rescue StandardError => e
      @logger.warn("Failed to store recording: #{e}")
    end
  end
end

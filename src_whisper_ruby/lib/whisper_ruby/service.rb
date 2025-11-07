# frozen_string_literal: true

require "json"
require "logger"
require "time"

require "nats/io/client"

module WhisperRuby
  ReceivedMessage = Struct.new(:subject, :reply, :data, keyword_init: true)

  class Service
    attr_reader :config

    def initialize(config:, logger: Logger.new($stdout))
      @config = config
      @logger = logger
      @nats_client = NATS::IO::Client.new
      @nats_mutex = Mutex.new
      @queue = SizedQueue.new(config.whisper.max_queue_size)
      @workers = []
      @running = false
      @transcriber = Transcriber.new(config: config.whisper, logger: @logger)
      @model_manager = ModelManager.new(logger: @logger)
      @nats_logger = nil
      @model_paths = nil
    end

    def start
      return if @running

      @running = true
      ensure_models_and_transcriber
      connect_nats
      setup_nats_logging
      start_workers
      subscribe_to_phrases

      @logger.info("WhisperRuby service is ready (subject=#{config.nats.whisper_subject})")
      loop do
        sleep 5
      end
    rescue StandardError => e
      @logger.error("Service crashed: #{e}")
      raise
    ensure
      @running = false
    end

    def running?
      @running
    end

    private

    def ensure_models_and_transcriber
      @model_paths = @model_manager.ensure_all(config.whisper)
      @transcriber.load!(
        model_path: @model_paths.asr,
        vad_model_path: @model_paths.vad
      )
    end

    def connect_nats
      servers = config.nats.url.split(",").map(&:strip).reject(&:empty?)
      options = {
        servers: servers.empty? ? [config.nats.url] : servers,
        reconnect_time_wait: 2,
        max_reconnect_attempts: -1,
        name: config.nats.connection_name
      }

      @nats_client.on_error do |err|
        @logger.error("NATS error: #{err}")
      end

      @nats_client.on_disconnect do |error|
        if error
          @logger.warn("Disconnected from NATS: #{error}")
        else
          @logger.warn("Disconnected from NATS")
        end
      end

      @nats_client.on_reconnect do
        @logger.info("Reconnected to NATS: #{connected_server_uri}")
      end

      @nats_client.connect(options)
      @logger.info("Connected to NATS #{connected_server_uri}")
    end

    def setup_nats_logging
      @nats_logger = NatsLogger.new(
        @nats_client,
        subject: config.nats.logs_subject,
        service_name: config.service_name
      )
      @nats_logger.log_info("WhisperRuby logger ready", category: "system")
    end

    def subscribe_to_phrases
      subject = config.nats.whisper_subject
      @nats_client.subscribe(subject) do |msg|
        enqueue_message(msg)
      end
      @nats_client.flush
      @logger.info("Subscribed to #{subject}")
    end

    def enqueue_message(msg)
      received = ReceivedMessage.new(subject: msg.subject, reply: msg.reply, data: msg.data)
      @queue.push(received)
    rescue ThreadError
      @logger.warn("Dropping message due to full queue")
    end

    def start_workers
      worker_count = config.whisper.worker_threads
      worker_count.times do |index|
        thread = Thread.new { worker_loop(index) }
        thread.name = "transcriber-#{index}" if thread.respond_to?(:name=)
        thread.abort_on_exception = true
        @workers << thread
      end
    end

    def worker_loop(worker_id)
      loop do
        msg = @queue.pop
        process_message(msg)
      rescue StandardError => e
        @logger.error("Worker #{worker_id} error: #{e}")
      end
    end

    def process_message(msg)
      packet = nil
      packet = PhrasePacket.from_bytes(msg.data)
      log_phrase_received(packet)
      start_ts = timestamp_now
      log_transcription_start(packet, start_ts)
      result = @transcriber.transcribe(packet)
      end_ts = timestamp_now

      payload = build_payload(packet, result, start_ts, end_ts)
      emit_transcription_log(packet, result, start_ts, end_ts)
      reply(msg, payload)
      @logger.info("Transcription done for #{packet.phrase_id || 'unknown'}")
    rescue PhrasePacketError => e
      @logger.error("Failed to parse phrase: #{e}")
      log_transcription_error("phrase_parse_failed", e, packet: nil, extra: {payload_size: msg.data&.bytesize})
      reply_with_error(msg, e.message)
    rescue StandardError => e
      @logger.error("Transcription failed: #{e}")
      log_transcription_error("transcription_failed", e, packet: packet)
      reply_with_error(msg, e.message, packet&.phrase_id)
    end

    def build_payload(packet, result, start_ts, end_ts)
      {
        type: "transcription",
        service: config.service_name,
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
      data = JSON.generate(payload)

      if msg.reply && !msg.reply.empty?
        publish(msg.reply, data)
      else
        publish("#{config.nats.whisper_subject}.result", data)
      end
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
      @nats_mutex.synchronize do
        @nats_client.publish(subject, data)
      end
    end

    def emit_transcription_log(packet, result, start_ts, end_ts)
      return unless @nats_logger && result.text && !result.text.empty?

      @nats_logger.log_transcription(
        text: result.text,
        segments: result.segments.length,
        audio_duration: result.audio_duration,
        transcription_time: result.transcription_time,
        start_timestamp: start_ts,
        end_timestamp: end_ts,
        phrase_id: packet.phrase_id
      )
    end

    def timestamp_now
      Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%L")
    end

    def log_phrase_received(packet)
      return unless @nats_logger && packet

      @nats_logger.log_event(
        event: "phrase_received",
        message: "Получена фраза из NATS",
        category: "transcription",
        phrase_id: packet.phrase_id,
        sample_rate: packet.sample_rate,
        audio_duration: packet.duration.round(3),
        audio_samples: packet.audio.length,
        metadata: packet.metadata
      )
    end

    def log_transcription_start(packet, start_ts)
      return unless @nats_logger && packet

      @nats_logger.log_transcription_start(
        audio_duration: packet.duration,
        audio_samples: packet.audio.length,
        sample_rate: packet.sample_rate,
        phrase_id: packet.phrase_id,
        start_timestamp: start_ts,
        metadata: packet.metadata
      )
    end

    def log_transcription_error(event, error, packet:, extra: nil)
      return unless @nats_logger

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

      @nats_logger.log_error(
        "#{event}: #{error.message}",
        category: "whisper",
        **payload
      )
    end

    def connected_server_uri
      @nats_client.connected_server&.to_s || "unknown"
    end
  end
end

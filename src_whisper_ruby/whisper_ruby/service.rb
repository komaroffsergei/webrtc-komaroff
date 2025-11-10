# frozen_string_literal: true

require "json"
require "logger"
require "time"
require "thread"

require "nats/io/client"

module WhisperRuby
  ReceivedMessage = Struct.new(:subject, :reply, :data, keyword_init: true)

  class Service
    attr_reader :config

    def initialize(config:, nats_client: nil)
      @config = config
      @nats_client = nats_client || NATSClient.new(config.nats.url)
      @queue = SizedQueue.new(config.whisper.max_queue_size)
      @workers = []
      @running = false
      @transcriber = Transcriber.new config: config.whisper
      @model_manager = ModelManager.new
      @model_paths = nil
      @nats_mutex = Mutex.new
      @log_queue = Queue.new
      @log_worker = nil
      @nats_logging_enabled = false
    end

    def start
      return if @running

      @running = true
      ensure_models_and_transcriber
      connect_nats
      configure_nats_logging
      start_workers
      subscribe_to_phrases
      @log_worker ||= start_log_worker

      LOGGER.info "WhisperRuby service is ready (subject=#{config.nats.whisper_subject})"
      loop do
        sleep 5
      end
    rescue StandardError => e
      LOGGER.exception "Service crashed:", e
      raise
    ensure
      @running = false
      stop_log_worker
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
      # NATSClient handles connection internally on initialization.
      @nats_client
    end

    def configure_nats_logging
      return unless @nats_client.respond_to?(:configure_logging)

      @nats_client.configure_logging(
        subject: config.nats.logs_subject,
        service_name: config.service_name
      )
      @nats_logging_enabled = true
    rescue StandardError => e
      LOGGER.warn("Failed to configure NATS logging: #{e}")
      @nats_logging_enabled = false
    end

    def subscribe_to_phrases
      Thread.new do
        @nats_client.loop_sub config.nats.whisper_subject do |msg|
          enqueue_message(msg)
        rescue StandardError => e
          LOGGER.error("NATS loop error: #{e}")
        end
      end
      LOGGER.info("Subscribed to #{config.nats.whisper_subject}")
    end

    def enqueue_message(msg)
      received = ReceivedMessage.new(subject: msg.subject, reply: msg.reply, data: msg.data)
      @queue.push(received)
    rescue ThreadError
      LOGGER.warn("Dropping message due to full queue")
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
        LOGGER.error("Worker #{worker_id} error: #{e}")
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
      LOGGER.info("Transcription done for #{packet.phrase_id || 'unknown'}")
    rescue PhrasePacketError => e
      LOGGER.error("Failed to parse phrase: #{e}")
      log_transcription_error("phrase_parse_failed", e, packet: nil, extra: {payload_size: msg.data&.bytesize})
      reply_with_error(msg, e.message)
    rescue StandardError => e
      LOGGER.error("Transcription failed: #{e}")
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
      data = JSON.generate(ensure_utf8(payload))

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
      return unless logging_enabled? && result.text && !result.text.empty?

      submit_log do
        @nats_client.log_transcription(
          text: result.text,
          segments: result.segments.length,
          audio_duration: result.audio_duration,
          transcription_time: result.transcription_time,
          start_timestamp: start_ts,
          end_timestamp: end_ts,
          phrase_id: packet.phrase_id
        )
      end
    end

    def submit_log(&block)
      return unless @log_queue && block

      @log_queue << block
    rescue StandardError => e
      LOGGER.warn("Failed to enqueue log task: #{e}")
      begin
        block.call
      rescue StandardError => inner
        LOGGER.warn("Fallback log execution failed: #{inner}")
      end
    end

    def start_log_worker
      Thread.new do
        loop do
          job = @log_queue.pop
          break if job.equal?(:stop)
          job.call
        rescue StandardError => e
          LOGGER.warn("Log worker error: #{e}")
        end
      end.tap { |thr| thr.report_on_exception = false }
    end

    def stop_log_worker
      return unless @log_worker

      @log_queue << :stop
      @log_worker.join(1)
    rescue StandardError => e
      LOGGER.warn("Failed to stop log worker: #{e}")
    ensure
      @log_worker = nil
    end

    def timestamp_now
      Time.now.utc.strftime("%Y-%m-%dT%H:%M:%S.%L")
    end

    def log_phrase_received(packet)
      return unless logging_enabled? && packet

      submit_log do
        @nats_client.log_event(
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
    end

    def log_transcription_start(packet, start_ts)
      return unless logging_enabled? && packet

      submit_log do
        @nats_client.log_transcription_start(
          audio_duration: packet.duration,
          audio_samples: packet.audio.length,
          sample_rate: packet.sample_rate,
          phrase_id: packet.phrase_id,
          start_timestamp: start_ts,
          metadata: packet.metadata
        )
      end
    end

    def log_transcription_error(event, error, packet:, extra: nil)
      return unless logging_enabled?

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

      submit_log do
        @nats_client.log_error(
          "#{event}: #{error.message}",
          category: "whisper",
          **payload
        )
      end
    end

    def logging_enabled?
      @nats_logging_enabled
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

    def connected_server_uri
      return "unknown" unless @nats_client

      if @nats_client.respond_to?(:connected_server)
        @nats_client.connected_server.to_s
      elsif @nats_client.respond_to?(:uri)
        @nats_client.uri.to_s
      else
        "unknown"
      end
    end
  end
end

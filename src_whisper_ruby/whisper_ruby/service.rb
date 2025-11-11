# frozen_string_literal: true

require "json"
require "logger"
require "time"
require "thread"

require "nats/io/client"

require_relative "transcription_logger"
require_relative "phrase_processor"
require_relative "transcription_worker_pool"

module WhisperRuby
  ReceivedMessage = Struct.new(:subject, :reply, :data, keyword_init: true)

  class Service
    attr_reader :config

    def initialize(config:, nats_client:)
      @config = config
      @nats_client = nats_client
      @running = false
      @transcriber = Transcriber.new config: config.whisper
      @model_manager = ModelManager.new
      @model_paths = nil
      @transcription_logger = TranscriptionLogger.new(nats_client: @nats_client)
      @phrase_processor = PhraseProcessor.new(
        transcriber: @transcriber,
        logger: @transcription_logger,
        config: config,
        nats_client: @nats_client
      )
      @worker_pool = TranscriptionWorkerPool.new(
        processor: @phrase_processor,
        queue_size: config.whisper.max_queue_size,
        worker_count: config.whisper.worker_threads
      )
      @subscription_sid = nil
      @shutdown = Queue.new
    end

    def start
      return if @running

      LOGGER.info("Service starting (subject=#{config.nats.whisper_subject})")
      @running = true
      ensure_models_and_transcriber
      connect_nats
      configure_nats_logging
      start_workers
      subscribe_to_phrases
      LOGGER.info "WhisperRuby service is ready (subject=#{config.nats.whisper_subject})"
      wait_for_shutdown
      self
    rescue StandardError => e
      LOGGER.error("Service crashed: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
      raise
    ensure
      @running = false
      stop_subscription
      stop_workers
      @transcription_logger.shutdown
    end

    def running?
      @running
    end

    def stop
      @shutdown << true
    rescue ThreadError
      # ignore repeated stops
    end

    private

    def wait_for_shutdown
      @shutdown.pop
    rescue ThreadError
      # queue interrupted, fall through to shutdown
    end

    def ensure_models_and_transcriber
      LOGGER.info("Ensuring models and loading transcriber")
      @model_paths = @model_manager.ensure_all(config.whisper)
      @transcriber.load!(
        model_path: @model_paths.asr,
        vad_model_path: @model_paths.vad
      )
      LOGGER.info("Transcriber loaded (asr=#{@model_paths.asr}, vad=#{@model_paths.vad})")
    end

    def connect_nats
      # NATSClient handles connection internally on initialization.
      LOGGER.info("Using NATS connection #{@nats_client.uri}")
      @nats_client
    end

    def configure_nats_logging
      LOGGER.info("Configuring NATS logging subject=#{config.nats.logs_subject}")
      @transcription_logger.configure( subject: config.nats.logs_subject )
    end

    def subscribe_to_phrases
      @subscription_sid = @nats_client.loop_sub(config.nats.whisper_subject) do |msg|
        LOGGER.info("Received NATS message subject=#{msg.subject} reply=#{msg.reply} size=#{msg.data&.bytesize}")
        enqueue_message(msg)
      rescue StandardError => e
        LOGGER.error("NATS loop error: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
      rescue Exception => e
        LOGGER.fatal("NATS loop fatal error: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
        raise
      end
      LOGGER.info("Subscribed to #{config.nats.whisper_subject}")
    end

    def enqueue_message(msg)
      received = ReceivedMessage.new(subject: msg.subject, reply: msg.reply, data: msg.data)
      LOGGER.info("Enqueuing message subject=#{received.subject} reply=#{received.reply} size=#{received.data&.bytesize}")
      @worker_pool.submit(received)
    end

    def start_workers
      LOGGER.info("Starting worker pool")
      @worker_pool.start
    end

    def stop_workers
      LOGGER.info("Stopping worker pool")
      @worker_pool.stop
    end

    def stop_subscription
      return unless @subscription_sid

      @nats_client.unsubscribe(@subscription_sid)
      @subscription_sid = nil
    rescue StandardError => e
      LOGGER.warn("Failed to unsubscribe from NATS: #{e}")
    end
  end
end

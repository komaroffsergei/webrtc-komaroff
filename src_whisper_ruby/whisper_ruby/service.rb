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
      connect_nats
      configure_nats_logging
      start_workers
      subscribe_to_phrases
      LOGGER.info "WhisperRuby service bootstrapped (subject=#{config.nats.whisper_subject})"
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

    # Load transcriber with prepared model paths (called from config.ru)
    def prepare_transcriber(model_path:, vad_model_path: nil)
      @transcriber.load!(model_path: model_path, vad_model_path: vad_model_path)
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

    def ensure_asr_model_async
      models_dir = config.whisper.models_dir
      model_name = config.whisper.model_name
      target = @model_manager.asr_target_path(models_dir:, model_name:)

      if File.file?(target)
        LOGGER.info("ASR model already present: #{target}")
        @transcription_logger.log_status("ready") if @transcription_logger.enabled?
        @transcriber.load!(model_path: target, vad_model_path: nil)
        return
      end

      Thread.new do
        begin
          @transcription_logger.log_status("downloading") if @transcription_logger.enabled?
          path = @model_manager.ensure_asr(models_dir:, model_name:)
          @transcriber.load!(model_path: path, vad_model_path: nil)
          @transcription_logger.log_status("ready") if @transcription_logger.enabled?
          LOGGER.info("ASR model ready at #{path}")
        rescue => e
          LOGGER.error("Failed to ensure ASR model: #{e}")
          raise
        end
      end
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

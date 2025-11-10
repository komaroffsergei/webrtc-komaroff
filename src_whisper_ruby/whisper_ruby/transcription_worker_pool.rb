# frozen_string_literal: true

require "thread"

module WhisperRuby
  class TranscriptionWorkerPool
    STOP_TOKEN = Object.new

    def initialize(processor:, queue_size:, worker_count:)
      @processor = processor
      @queue = SizedQueue.new(queue_size)
      @worker_count = worker_count
      @workers = []
    end

    def start
      return unless @workers.empty?

      LOGGER.info("Initializing worker pool (threads=#{@worker_count}, queue_size=#{@queue.max})")
      @worker_count.times do |index|
        thread = Thread.new { worker_loop(index) }
        thread.name = "transcriber-#{index}" if thread.respond_to?(:name=)
        thread.abort_on_exception = true
        @workers << thread
      end
    end

    def submit(message)
      @queue.push(message)
    rescue ThreadError
      LOGGER.warn("Dropping message due to full queue")
    end

    def stop
      return if @workers.empty?

      LOGGER.info("Stopping worker pool (active_threads=#{@workers.count(&:alive?)})")
      @workers.size.times { enqueue_stop_signal }
      @workers.each { |thread| thread.join(1) }
      @workers.clear
    end

    private

    def worker_loop(worker_id)
      LOGGER.info("Worker #{worker_id} started (thread=#{Thread.current.object_id})")
      loop do
        msg = @queue.pop
        break if msg.equal?(STOP_TOKEN)

        LOGGER.info("Worker #{worker_id} processing subject=#{msg.subject} reply=#{msg.reply}")
        @processor.process(msg)
      rescue StandardError => e
        LOGGER.error("Worker #{worker_id} error: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
      rescue Exception => e
        LOGGER.fatal("Worker #{worker_id} fatal error: #{e.class}: #{e.message}\n#{Array(e.backtrace).join("\n")}")
        raise
      end
      LOGGER.info("Worker #{worker_id} exiting")
    end

    def enqueue_stop_signal
      @queue.push(STOP_TOKEN, true)
    rescue ThreadError
      begin
        @queue.pop(true)
      rescue ThreadError
        sleep 0.01
      end
      retry
    end
  end
end

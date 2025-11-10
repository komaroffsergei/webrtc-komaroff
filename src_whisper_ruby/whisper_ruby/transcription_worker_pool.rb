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

      @workers.size.times { enqueue_stop_signal }
      @workers.each { |thread| thread.join(1) }
      @workers.clear
    end

    private

    def worker_loop(worker_id)
      loop do
        msg = @queue.pop
        break if msg.equal?(STOP_TOKEN)

        @processor.process(msg)
      rescue StandardError => e
        LOGGER.error("Worker #{worker_id} error: #{e}")
      end
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

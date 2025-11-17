# frozen_string_literal: true

require "time"

module WhisperRuby
  class Logger
    def initialize(nc, logs_subject)
      @nc = nc
      @subject = logs_subject
      @last_percent = -1
    end

    def log(message, type: "info", service: STACK_SERVICE_NAME)
      payload = {
        time: Time.now.utc.iso8601(3),
        service: service,
        type: type,
        message: message
      }
      @nc.publish(@subject, payload.to_json)
    end

    def progress(percent)
      return if percent <= @last_percent
      @last_percent = percent
      log(percent, type: "progress", service: STACK_SERVICE_NAME)
    end

    def flush
      @nc.flush if @nc.respond_to?(:flush)
    end
  end
end

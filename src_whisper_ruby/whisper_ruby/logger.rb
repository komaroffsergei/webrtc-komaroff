# frozen_string_literal: true

require "time"

module WhisperRuby
  class Logger
    def initialize(nc, logs_subject)
      @nc = nc
      @subject = logs_subject
    end

    def log(message, type: "info", service: STACK_SERVICE_NAME, name: "")
      payload = {
        time: Time.now.utc.iso8601(3),
        service: service,
        type: type,
        message: message,
        name: name
      }
      @nc.publish(@subject, payload.to_json)
    end

    def flush
      @nc.flush if @nc.respond_to?(:flush)
    end
  end
end

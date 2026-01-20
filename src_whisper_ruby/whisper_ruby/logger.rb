# frozen_string_literal: true

require "time"
require "json"
require "securerandom"

module WhisperRuby
  class Logger
    def initialize(nc, logs_subject)
      @nc = nc
      @subject = logs_subject
    end

    def publish(type:, kind:, data:, service: STACK_SERVICE_NAME, name: "")
      payload = {
        time: Time.now.utc.iso8601(3),
        service: service,
        type: type,
        kind: kind,
        data: data,
        name: name.to_s,
        uid: SecureRandom.uuid
      }
      @nc.publish(@subject, payload.to_json)
    end

    def info(message, service: STACK_SERVICE_NAME, name: "")
      safe_message = message.to_s.encode("UTF-8", invalid: :replace, undef: :replace)
      publish(type: "log", kind: "info", data: { text: safe_message }, service: service, name: name)
    end

    def error(message, service: STACK_SERVICE_NAME, name: "")
      safe_message = message.to_s.encode("UTF-8", invalid: :replace, undef: :replace)
      publish(type: "log", kind: "error", data: { text: safe_message }, service: service, name: name)
    end

    def command(kind, data, service: STACK_SERVICE_NAME, name: "")
      publish(type: "command", kind: kind.to_s, data: data, service: service, name: name)
    end

    def flush
      @nc.flush if @nc.respond_to?(:flush)
    end
  end
end

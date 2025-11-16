# frozen_string_literal: true

require "nats"
require "json"
require "time"
require "thread"

require_relative "../utils/text_utils"

class NATSClient

  def initialize(url, options = {})
    @nats = NATS::Client.new
    @nats.connect(url, options)
    @log_subject = nil
  end

  def req(request, params = {})
    JSON(@nats.request(request, params.to_json).data, symbolize_names: true)
  end

  def publish(subj, message)
    payload = message.is_a?(String) ? message : message.to_json
    @nats.publish(subj, payload)
    flush_connection
  end

  def loop_sub(subject, &block)
    @nats.subscribe(subject, &block)
  end

  def unsubscribe(sid)
    return unless sid

    if @nats.respond_to?(:unsubscribe, true)
      @nats.__send__(:unsubscribe, sid)
    end
  end

  def connected? = @nats&.connected?
  def connected_server = @nats&.uri
  def uri = @nats&.uri

  def configure_logging(subject:)
    @log_subject = subject
  end

  def log(message:, type: "info", subject: "src_whisper_ruby", name: nil)
    target = subject || @log_subject
    return unless target && connected?

    payload = {
      time: Time.now.utc.iso8601(3),
      service: @service_name,
      type: type,
      name: name || "",
      message: message.to_s
    }

    data = JSON.generate(WhisperRuby::TextUtils.ensure_utf8(payload))
    publish(target, data)
  end

  private

  def flush_connection
    @nats.flush if @nats.respond_to?(:flush)
  end
end

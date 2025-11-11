# frozen_string_literal: true

require "nats"
require "json"
require "time"
require "thread"

require_relative "../utils/text_utils"

ENV["NATS_RECONNECT"] = "true"
# ENV['NATS_VERBOSE'] = 'true'
ENV["NATS_RECONNECT_TIME_WAIT"] = "2"
ENV["NATS_MAX_RECONNECT_ATTEMPTS"] = "-1"

class NATSClient

  def initialize(url, options = {})
    @nats = NATS::Client.new
    @nats.on_close { LOGGER.info "NATS Client closed", _1 }
    @nats.on_error { LOGGER.error "NATS Client failed", _1 }
    @nats.on_disconnect { LOGGER.info "NATS Client disconnected", _1 }
    @nats.on_reconnect { LOGGER.info "NATS Client reconnected", _1}
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
    @log_service_name = normalize_service_name
  end

  def log_info(message, category: "general", subject: nil, **extra)
    publish_log(subject, "info", message, category, extra)
  end

  def log_warning(message, category: "general", subject: nil, **extra)
    publish_log(subject, "warning", message, category, extra)
  end

  def log_error(message, category: "general", subject: nil, **extra)
    publish_log(subject, "error", message, category, extra)
  end

  def log_event(event:, message:, category: "system", level: "info", subject: nil, **extra)
    extra[:event] = event
    publish_log(subject, level, message, category, extra)
  end

  def log_transcription_start(audio_duration:, audio_samples:, sample_rate:, phrase_id: nil,
                              start_timestamp: nil, metadata: nil, subject: nil)
    ts = start_timestamp || Time.now.utc.iso8601(3)
    extra = {
      audio_duration: audio_duration,
      audio_samples: audio_samples,
      sample_rate: sample_rate,
      start: ts,
      event: "transcription_started"
    }
    extra[:phrase_id] = phrase_id if phrase_id
    extra[:metadata] = metadata if metadata

    message = format(
      "Transcription started: audio=%.2fs samples=%d sample_rate=%d",
      audio_duration.to_f,
      audio_samples.to_i,
      sample_rate.to_i
    )

    publish_log(subject, "info", message, "whisper", extra)
    ts
  end

  def log_transcription(text:, segments:, audio_duration:, transcription_time:,
                        start_timestamp:, end_timestamp:, phrase_id: nil,
                        event: "transcription_completed", subject: nil)
    rtf = if audio_duration.to_f.positive? && transcription_time.to_f.positive?
            transcription_time.to_f / audio_duration.to_f
          else
            0.0
          end

    extra = {
      text: text,
      segments: segments,
      audio_duration: audio_duration,
      transcription_time: transcription_time,
      rtf: rtf.round(2),
      start: start_timestamp,
      end: end_timestamp,
      event: event
    }
    extra[:phrase_id] = phrase_id if phrase_id

    message = format(
      "Transcription completed: audio=%<audio>.2fs text=%<text>s time=%<time>.2fs segments=%<segments>d",
      audio: audio_duration,
      text: text,
      time: transcription_time,
      segments: segments
    )

    publish_log(subject, "info", message, "whisper", extra)
  end

  private



  def publish_log(subject, level, message, category, extra)
    subj = subject || @log_subject
    return unless subj && connected?

    payload = {
      type: "log",
      level: level,
      category: category,
      message: message,
      timestamp: Time.now.utc.iso8601(3)
    }
    payload.merge!(extra.compact) if extra && !extra.empty?

    data = JSON.generate(WhisperRuby::TextUtils.ensure_utf8(payload))
    publish(subj, data)
  rescue StandardError => e
    warn("Failed to publish log to NATS: #{e}")
  end

  def flush_connection
    return unless @nats.respond_to?(:flush)

    @nats.flush
  rescue StandardError => e
    LOGGER.warn("NATS flush failed: #{e}") if defined?(LOGGER)
  end
end

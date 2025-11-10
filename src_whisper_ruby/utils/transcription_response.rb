# frozen_string_literal: true

module WhisperRuby
  module TranscriptionResponse
    module_function

    def success(config:, packet:, result:, start_ts:, end_ts:)
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

    def error(error:, phrase_id: nil)
      {
        type: "transcription",
        error: error,
        phrase_id: phrase_id
      }
    end
  end
end

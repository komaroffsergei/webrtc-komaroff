# frozen_string_literal: true

require "json"

module WhisperRuby
  class PhrasePacketError < StandardError; end

  class PhrasePacket
    attr_reader :phrase_id, :sample_rate, :sample_width, :raw_audio, :metadata

    def initialize(phrase_id:, sample_rate:, sample_width:, raw_audio:, metadata:)
      @phrase_id = phrase_id
      @sample_rate = sample_rate
      @sample_width = sample_width
      @raw_audio = raw_audio
      @metadata = metadata
    end

    def self.from_bytes(payload)
      raise PhrasePacketError, "payload too short for metadata header" if payload.nil? || payload.bytesize < 4

      meta_len = payload.unpack1("N")
      raise PhrasePacketError, "invalid metadata length" if meta_len.negative? || payload.bytesize < 4 + meta_len

      meta_raw = payload.byteslice(4, meta_len) || ""
      metadata = meta_raw.empty? ? {} : JSON.parse(meta_raw)

      audio_bytes = payload.byteslice(4 + meta_len, payload.bytesize - 4 - meta_len) || ""
      raise PhrasePacketError, "audio payload is empty" if audio_bytes.empty?

      sample_width = Integer(metadata.fetch("sample_width", 2))
      unless [2, 4].include?(sample_width)
        raise PhrasePacketError, "unsupported sample width: #{sample_width}"
      end

      sample_rate = Integer(metadata.fetch("sample_rate", 16_000))
      phrase_id = metadata["phrase_id"]&.to_s

      new(
        phrase_id: phrase_id,
        sample_rate: sample_rate,
        sample_width: sample_width,
        raw_audio: audio_bytes,
        metadata: metadata
      )
    rescue JSON::ParserError => e
      raise PhrasePacketError, "invalid metadata json: #{e.message}"
    end

    def frame_count
      bytes_per_sample = sample_width
      raw_audio.bytesize / bytes_per_sample
    end

    def audio_duration
      return 0.0 if sample_rate.zero?

      frame_count / sample_rate.to_f
    end

    def audio_bytes
      raw_audio.bytesize
    end
  end
end

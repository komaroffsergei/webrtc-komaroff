# frozen_string_literal: true

require "json"

module WhisperRuby
  class PhrasePacket
    attr_reader :phrase_id, :sample_rate, :duration, :audio

    def self.parse(data)
      meta_len  = data[0, 4].unpack1("N")
      meta_json = data[4, meta_len]
      pcm_bytes = data[(4 + meta_len)..]

      meta = JSON.parse(meta_json)
      pcm_i16 = pcm_bytes.unpack("s*")
      pcm_f32 = pcm_i16.map { |v| v / 32768.0 }

      new(
        phrase_id:   meta["phrase_id"],
        duration:    meta["duration"],
        sample_rate: meta["sample_rate"],
        audio:       pcm_f32
      )
    end

    def initialize(phrase_id:, duration:, sample_rate:, audio:)
      @phrase_id   = phrase_id
      @duration    = duration
      @sample_rate = sample_rate
      @audio       = audio
    end
  end
end

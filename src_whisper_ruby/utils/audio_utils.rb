# frozen_string_literal: true

require "json"
require "narray"

module WhisperRuby
  PhrasePacketError = Class.new(StandardError)

  class PhrasePacket
    attr_reader :phrase_id, :sample_rate, :sample_width, :audio, :metadata

    def initialize(phrase_id:, sample_rate:, sample_width:, audio:, metadata:)
      @phrase_id = phrase_id
      @sample_rate = sample_rate
      @sample_width = sample_width
      @audio = audio
      @metadata = metadata
    end

    def duration
      return 0.0 if sample_rate.to_i <= 0 || audio.empty?

      audio.length.to_f / sample_rate.to_f
    end
  end

  module AudioUtils
    INT16_SCALE = 32_768.0
    INT32_SCALE = 2_147_483_648.0

    module_function

    def parse_phrase_packet(payload)
      metadata, audio_bytes = extract_metadata(payload)

      sample_width = Integer(metadata.fetch("sample_width", 2))
      sample_rate = Integer(metadata.fetch("sample_rate", 16_000))
      phrase_id = metadata["phrase_id"]&.to_s
      audio = decode_audio(audio_bytes, sample_width)

      PhrasePacket.new(
        phrase_id: phrase_id,
        sample_rate: sample_rate,
        sample_width: sample_width,
        audio: audio,
        metadata: metadata
      )
    end

    def resample(samples, source_rate, target_rate)
      return samples if source_rate.to_i <= 0 || source_rate == target_rate || samples.length <= 1

      target_length = [(samples.length.to_f / source_rate * target_rate).round, 1].max
      return samples if target_length == samples.length

      data = samples.is_a?(NArray) ? samples : NArray.to_na(samples)
      step = (data.length - 1).to_f / [target_length - 1, 1].max
      positions = NArray.sfloat(target_length).indgen! * step
      left_idx = positions.floor.to_i
      right_idx = left_idx + 1
      right_idx[right_idx >= data.length] = data.length - 1
      fractions = positions - positions.floor

      data[left_idx] * (1.0 - fractions) + data[right_idx] * fractions
    end

    def extract_metadata(payload)
      raise PhrasePacketError, "payload too short" if payload.nil? || payload.bytesize < 4

      meta_len = payload.byteslice(0, 4).unpack1("N")
      raise PhrasePacketError, "invalid metadata length" if meta_len.negative? || payload.bytesize < 4 + meta_len

      meta_raw = payload.byteslice(4, meta_len)
      metadata = meta_raw && !meta_raw.empty? ? JSON.parse(meta_raw) : {}

      audio_bytes = payload.byteslice(4 + meta_len, payload.bytesize)
      raise PhrasePacketError, "audio payload is empty" unless audio_bytes && !audio_bytes.empty?

      [metadata, audio_bytes]
    rescue JSON::ParserError => e
      raise PhrasePacketError, "invalid metadata json: #{e.message}"
    end

    def decode_audio(bytes, sample_width)
      raise PhrasePacketError, "unsupported sample width: #{sample_width}" unless [2, 4].include?(sample_width)
      raise PhrasePacketError, "audio size mismatch" unless (bytes.bytesize % sample_width).zero?

      case sample_width
      when 2
        bytes.unpack("s<*").map { |sample| sample.to_f / INT16_SCALE }
      when 4
        bytes.unpack("l<*").map { |sample| sample.to_f / INT32_SCALE }
      end
    end
    private_class_method :decode_audio
  end
end

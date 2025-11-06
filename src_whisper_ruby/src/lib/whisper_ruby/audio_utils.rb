# frozen_string_literal: true

module WhisperRuby
  module AudioUtils
    module_function

    def decode_pcm(raw_audio, sample_width)
      case sample_width
      when 2
        raw_audio.unpack("s<*").map { |v| v.to_f / 32768.0 }
      when 4
        raw_audio.unpack("l<*").map { |v| v.to_f / 2_147_483_648.0 }
      else
        raise ArgumentError, "unsupported sample width: #{sample_width}"
      end
    end

    def resample(samples, orig_rate, target_rate)
      return samples if samples.empty?
      return samples if orig_rate.to_f <= 0.0 || target_rate.to_f <= 0.0
      return samples if orig_rate == target_rate

      duration = samples.length.to_f / orig_rate
      target_length = (duration * target_rate).round
      return samples if target_length <= 1

      step = (samples.length - 1).to_f / (target_length - 1)

      Array.new(target_length) do |i|
        index = i * step
        left = index.floor
        right = index.ceil
        if left == right
          samples[left]
        else
          weight = index - left
          samples[left] * (1.0 - weight) + samples[right] * weight
        end
      end
    end
  end
end

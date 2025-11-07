# frozen_string_literal: true

module WhisperRuby
  module AudioUtils
    module_function

    def resample(samples, source_rate, target_rate)
      return samples if source_rate.to_i <= 0 || source_rate == target_rate || samples.length <= 1

      duration = samples.length.to_f / source_rate.to_f
      target_length = (duration * target_rate).round
      target_length = 1 if target_length < 1
      return samples if target_length == samples.length

      resampled = Array.new(target_length)
      max_index = samples.length - 1
      step = max_index.to_f / [target_length - 1, 1].max

      target_length.times do |i|
        pos = i * step
        left = pos.floor
        right = [left + 1, max_index].min
        frac = pos - left
        resampled[i] = (samples[left] * (1.0 - frac)) + (samples[right] * frac)
      end

      resampled
    end
  end
end

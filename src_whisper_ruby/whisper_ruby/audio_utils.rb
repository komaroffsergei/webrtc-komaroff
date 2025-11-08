# frozen_string_literal: true

require 'narray'

module WhisperRuby
  module AudioUtils
    module_function

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
  end
end

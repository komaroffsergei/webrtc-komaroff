# frozen_string_literal: true

require_relative '../../whisper_ruby/audio_utils'

RSpec.describe WhisperRuby::AudioUtils do
  describe '.resample' do
    let(:samples) { [0.0, 1.0, 2.0, 3.0, 4.0] }

    context 'when upsampling' do
      it 'increases sample count correctly' do
        result = described_class.resample(samples, 5, 10)
        expect(result.length).to eq(10)
      end

      it 'preserves boundary values' do
        result = described_class.resample(samples, 5, 10)
        expect(result.to_a.first).to be_within(0.001).of(0.0)
        expect(result.to_a.last).to be_within(0.001).of(4.0)
      end
    end

    context 'when downsampling' do
      it 'decreases sample count correctly' do
        result = described_class.resample(samples, 5, 3)
        expect(result.length).to eq(3)
      end

      it 'preserves boundary values' do
        result = described_class.resample(samples, 5, 3)
        expect(result.to_a.first).to be_within(0.001).of(0.0)
        expect(result.to_a.last).to be_within(0.001).of(4.0)
      end
    end

    context 'when source and target rates are the same' do
      it 'returns the original samples' do
        result = described_class.resample(samples, 5, 5)
        expect(result).to eq(samples)
      end
    end

    context 'with edge cases' do
      it 'handles single sample' do
        result = described_class.resample([1.0], 5, 10)
        expect(result).to eq([1.0])
      end

      it 'handles empty array' do
        result = described_class.resample([], 5, 10)
        expect(result).to eq([])
      end

      it 'handles invalid source rate' do
        result = described_class.resample(samples, 0, 10)
        expect(result).to eq(samples)
      end
    end

    context 'linear interpolation accuracy' do
      it 'interpolates correctly between two values' do
        result = described_class.resample([0.0, 10.0], 2, 5)
        expected = [0.0, 2.5, 5.0, 7.5, 10.0]
        
        result.to_a.each_with_index do |value, index|
          expect(value).to be_within(0.001).of(expected[index])
        end
      end

      it 'produces monotonic results for monotonic input' do
        result = described_class.resample([1.0, 2.0, 3.0, 4.0], 4, 10)
        values = result.to_a
        
        values.each_cons(2) do |a, b|
          expect(b).to be >= a
        end
      end
    end
  end
end

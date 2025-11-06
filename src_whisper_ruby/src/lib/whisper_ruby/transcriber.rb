# frozen_string_literal: true

require "time"
require "whisper"
require "etc"

require_relative "audio_utils"

module WhisperRuby
  class Transcriber
    class Error < StandardError; end

    def initialize(config:, logger:)
      @config = config
      @logger = logger
      @mutex = Mutex.new
      @processors = resolve_processors

      @context = build_context
    end

    def transcribe(packet, timeout:)
      samples = decode_samples(packet)
      samples = AudioUtils.resample(samples, packet.sample_rate, @config.target_sample_rate)

      start_ts = Time.now.utc.iso8601
      start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)

      params = build_params
      text = ""
      segments = []

      @mutex.synchronize do
        run_transcription(params, samples, segments)
        text = segments.map { |segment| segment[:text] }.join(" ").strip
      end

      transcription_time = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time
      end_ts = Time.now.utc.iso8601
      audio_duration = compute_duration(samples)

      {
        "status" => "ok",
        "text" => text,
        "segments" => segments.length,
        "segment_details" => segments,
        "audio_duration" => audio_duration,
        "transcription_time" => transcription_time,
        "start_timestamp" => start_ts,
        "end_timestamp" => end_ts
      }
    rescue StandardError => e
      raise Error, e.message
    end

    def shutdown
      # whispercpp manages native resources automatically; nothing to clean up.
    end

    private

    def build_context
      model_file = resolve_model_path(@config.model_ggml_path)
      Whisper::Context.new(model_file)
    rescue StandardError => e
      raise Error, "failed to initialize whisper context: #{e.message}"
    end

    def build_params
      Whisper::Params.new(
        language: @config.language,
        translate: false,
        print_progress: false,
        print_realtime: false,
        print_timestamps: false,
        no_context: true,
        single_segment: false,
        suppress_blank: true
      )
    end

    def decode_samples(packet)
      AudioUtils.decode_pcm(packet.raw_audio, packet.sample_width)
    end

    def run_transcription(params, samples, segments)
      @context.full_parallel(params, samples, samples.length, @processors)

      @context.each_segment do |segment|
        segments << {
          text: segment.text.strip,
          start: segment.start_time / 1000.0,
          end: segment.end_time / 1000.0,
          no_speech_prob: segment.no_speech_prob,
          speaker_turn_next: segment.speaker_turn_next?
        }
      end
    end

    def resolve_model_path(path)
      expanded = File.expand_path(path)
      return expanded if File.file?(expanded)

      if File.directory?(expanded)
        candidate = Dir[File.join(expanded, "*.bin")].sort.first
        return candidate if candidate
      end

      raise Error, "model file not found at #{expanded}"
    end

    def compute_duration(samples)
      rate = @config.target_sample_rate.to_f
      return 0.0 if rate <= 0.0

      samples.length.to_f / rate
    end

    def resolve_processors
      Etc.respond_to?(:nprocessors) ? [Etc.nprocessors, 1].max : 1
    rescue StandardError
      1
    end
  end
end

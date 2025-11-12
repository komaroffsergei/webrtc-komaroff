# frozen_string_literal: true

module WhisperRuby; end unless defined?(WhisperRuby)
require "whisper"

module WhisperRuby
  TranscriptionResult = Struct.new(:text, :segments, :audio_duration, :transcription_time, keyword_init: true)

  class Transcriber
    TARGET_SAMPLE_RATE = 16_000

    def initialize(config:)
      @config = config
      @model_path = nil
      @vad_model_path = nil
      @thread_key = :"whisper_ctx_#{object_id}"
      @thread_contexts = {}
      @thread_contexts_mutex = Mutex.new
      @loaded = false
    end

    def load!(model_path:, vad_model_path:)
      return if @loaded

      @model_path = model_path
      @vad_model_path = vad_model_path
      @loaded = true
      LOGGER.info "Whisper transcriber prepared (model=#{@model_path}, vad=#{@vad_model_path})"
    end

    def transcribe(packet)
      raise "Whisper model is not loaded" unless @loaded

      audio = packet.audio
      if packet.sample_rate != TARGET_SAMPLE_RATE
        audio = AudioUtils.resample(audio, packet.sample_rate, TARGET_SAMPLE_RATE)
      end

      context = thread_local_context
      params = build_params
      start_time = Process.clock_gettime(Process::CLOCK_MONOTONIC)

      # run model
      context.full(params, audio)

      segments = collect_segments(context)
      # if segments.empty?
      #   fallback_stats(audio, packet)
      #   params_no_vad = build_params(vad_enabled: false)
      #   context_info = format(
      #     "packet_id=%<id>s, duration=%<duration>.3f, samples=%<samples>d",
      #     id: packet.phrase_id || "unknown",
      #     duration: packet.duration,
      #     samples: audio.length
      #   )
      #   LOGGER.warn "No speech detected by Whisper VAD, retrying without VAD (#{context_info})"
      #   run_model(context, params_no_vad, audio)
      #   segments = collect_segments(context)
      # end
      transcription_time = Process.clock_gettime(Process::CLOCK_MONOTONIC) - start_time
      text = segments.map { |segment| segment[:text] }.join(" ").strip

      TranscriptionResult.new(
        text: text,
        segments: segments,
        audio_duration: packet.duration,
        transcription_time: transcription_time
      )
    end

    private

    def thread_local_context
      ctx = Thread.current[@thread_key]
      return ctx if ctx

      new_ctx = Whisper::Context.new(@model_path)
      Thread.current[@thread_key] = new_ctx
      @thread_contexts_mutex.synchronize do
        @thread_contexts[Thread.current.object_id] = new_ctx
      end
      LOGGER.debug "Initialized whisper context for worker thread #{Thread.current.object_id}"
      new_ctx
    end

    def collect_segments(context)
      segments = []
      context.each_segment do |segment|
        segments << {
          text: segment.text.strip,
          start: (segment.start_time.to_f / 1000.0).round(3),
          end: (segment.end_time.to_f / 1000.0).round(3),
          no_speech_prob: segment.no_speech_prob,
          speaker_turn_next: segment.speaker_turn_next?
        }
      end
      segments
    end

    def build_params(vad_enabled: nil)
      # Disable VAD if no VAD model path provided
      effective_vad = vad_enabled.nil? ? !@vad_model_path.nil? : vad_enabled

      params = Whisper::Params.new(
        language: @config.language,
        translate: @config.translate,
        print_special: false,
        print_progress: false,
        print_realtime: false,
        print_timestamps: false,
        suppress_blank: true,
        suppress_nst: true,
        token_timestamps: false,
        max_len: 0,
        split_on_word: true,
        vad: effective_vad,
        vad_model_path: effective_vad ? @vad_model_path : nil
      )
      params.temperature = @config.temperature
      params.temperature_inc = @config.temperature_inc
      params.vad_params = Whisper::VAD::Params.new(
        threshold: @config.vad_threshold,
        min_speech_duration_ms: @config.vad_min_speech_ms,
        min_silence_duration_ms: @config.vad_min_silence_ms,
        max_speech_duration_s: @config.vad_max_speech_ms / 1000.0,
        speech_pad_ms: @config.vad_speech_pad_ms
      )
      params
    end
  end
end

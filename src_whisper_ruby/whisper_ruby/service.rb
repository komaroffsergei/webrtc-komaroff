# frozen_string_literal: true

require "whisper"
require "tempfile"
require "time"

require_relative "logger"
require_relative "model_downloader"
require_relative "phrase_packet"

module WhisperRuby
  class Service
    def initialize(nc:)
      @nc  = nc
      @log = Logger.new(@nc, NATS_LOGS_SUBJECT)

      @model_status = :downloading
      @ctx = nil
    end

    def run
      start_model_loader_thread
      subscribe_frames
      @log.log("Whisper Ruby service started")
      sleep
    end

    private

    def start_model_loader_thread
      Thread.new do
        begin
          WhisperRuby::ModelDownloader.download_model(
            @log,
            model_url: WHISPER_MODEL_URL,
            model_sha: WHISPER_MODEL_SHA1,
            model_dir: MODELS_DIR,
            model_path: MODEL_PATH
          )

          begin
            @ctx = Whisper::Context.new(MODEL_PATH)
            @model_status = :ready
            @log.log("Model loaded")

          rescue Whisper::Error => e
            @model_status = :error
            @log.log("Whisper init failed: #{e}", type: "error")

          rescue Errno::ENOENT => e
            @model_status = :error
            @log.log("Model file missing: #{e}", type: "error")

          rescue => e
            @model_status = :error
            @log.log("Unexpected init error: #{e} (#{e.class})", type: "error")
          end


        rescue => e
          @model_status = :error
          @log.log("Model download failed: #{e}", type: "error")
        end
      end


    end

    def subscribe_frames
      @nc.subscribe(NATS_FRAMES_SUBJECT) { |msg| handle_frame(msg) }
      @log.log("Subscribed to #{NATS_FRAMES_SUBJECT}")
    end

    def handle_frame(msg)
      return unless @model_status == :ready

      Thread.new do
        begin
          packet = PhrasePacket.parse(msg.data)
          @log.log("Phrase received id=#{packet.phrase_id} dur=#{packet.duration}")

          started = Process.clock_gettime(Process::CLOCK_MONOTONIC)
          @log.log("Transcription started phrase_id=#{packet.phrase_id}")

          text = transcribe_packet(packet)

          transcription_time = Process.clock_gettime(Process::CLOCK_MONOTONIC) - started

          payload = {
            time: Time.now.utc.iso8601(3),
            service: "whisper_ruby",
            type: "info",
            message: {
              phrase_id: packet.phrase_id,
              text: text,
              duration: packet.duration,
              transcribe_time: transcription_time
            }
          }

          @nc.publish(NATS_LOGS_SUBJECT, payload.to_json)
          @log.log("Transcription finished phrase_id=#{packet.phrase_id} time=#{transcription_time.round(3)}s")
        rescue => e
          @log.log("Transcription error: #{e}", type: "error")
        end
      end
    end

    def transcribe_packet(packet)
      pcm_i16 = packet.audio.map { |f| (f * 32767).clamp(-32_768, 32_767).to_i }.pack("s*")

      min_bytes = (packet.sample_rate * MIN_PHRASE_MS / 1000) * 2
      pcm_i16 += ("\x00" * (min_bytes - pcm_i16.bytesize)) if pcm_i16.bytesize < min_bytes

      wav = Tempfile.new(%w[phrase .wav])
      wav.binmode
      wav.write(build_wav_header(pcm_i16.bytesize, packet.sample_rate, 1))
      wav.write(pcm_i16)
      wav.flush

      params = Whisper::Params.new
      params.language = "ru"
      params.translate = false
      params.vad = false
      params.no_context = true

      @ctx.transcribe(wav.path, params)

      segments = @ctx.full_n_segments
      text = +""
      segments.times { |i| text << @ctx.full_get_segment_text(i) }

      wav.close!
      text.strip
    end


    def build_wav_header(data_size, sample_rate, channels)
      byte_rate   = sample_rate * channels * 2
      block_align = channels * 2

      [
        "RIFF",
        36 + data_size,
        "WAVE",
        "fmt ",
        16,
        1,
        channels,
        sample_rate,
        byte_rate,
        block_align,
        16,
        "data",
        data_size
      ].pack("A4VA4A4VvvVVvvA4V")
    end
  end
end

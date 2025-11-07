# frozen_string_literal: true

require "fileutils"
require "net/http"
require "uri"

module WhisperRuby
  ModelPaths = Struct.new(:asr, :vad, keyword_init: true)

  class ModelManager
    ASR_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"
    VAD_BASE_URL = "https://huggingface.co/ggml-org/whisper-vad/resolve/main"

    def initialize(logger:)
      @logger = logger
    end

    def ensure_all(whisper_config)
      asr_path = ensure_model(
        target_path: whisper_config.resolved_model_reference,
        explicit_url: whisper_config.model_url,
        default_base: ASR_BASE_URL,
        force_download: whisper_config.force_download
      )

      vad_path = ensure_model(
        target_path: whisper_config.resolved_vad_reference,
        explicit_url: nil,
        default_base: VAD_BASE_URL,
        force_download: whisper_config.force_download
      )

      ModelPaths.new(asr: asr_path, vad: vad_path)
    end

    private

    def ensure_model(target_path:, explicit_url:, default_base:, force_download:)
      return target_path if File.file?(target_path) && !force_download

      FileUtils.mkdir_p(File.dirname(target_path))

      url = explicit_url || File.join(default_base, File.basename(target_path))

      download_file(url, target_path)
    end

    def download_file(url, destination)
      tmp_path = "#{destination}.download"
      @logger.info("Downloading model #{File.basename(destination)}")

      fetch_with_redirects(URI(url)) do |response|
        File.open(tmp_path, "wb") do |file|
          response.read_body do |chunk|
            file.write(chunk)
          end
        end
      end

      FileUtils.mv(tmp_path, destination)
      @logger.info("Model stored at #{destination}")
      destination
    ensure
      FileUtils.rm_f(tmp_path) if tmp_path && File.exist?(tmp_path)
    end

    def fetch_with_redirects(uri, limit = 5, &block)
      raise "Too many redirects while downloading #{uri}" if limit <= 0

      http = Net::HTTP.new(uri.host, uri.port)
      http.use_ssl = uri.scheme == "https"
      http.open_timeout = Integer(ENV.fetch("MODEL_DOWNLOAD_OPEN_TIMEOUT", "30"))
      http.read_timeout = Integer(ENV.fetch("MODEL_DOWNLOAD_READ_TIMEOUT", "600"))

      request = Net::HTTP::Get.new(uri)
      request["User-Agent"] = "whisper-ruby-service/1.0"

      http.request(request) do |response|
        case response
        when Net::HTTPRedirection
          location = response["location"]
          raise "Redirect without location for #{uri}" unless location

          next_uri = URI(location)
          next_uri = uri + location if next_uri.relative?
          return fetch_with_redirects(next_uri, limit - 1, &block)
        when Net::HTTPSuccess
          yield response
        else
          raise "Failed to download #{uri} (#{response.code} #{response.message})"
        end
      end
    end
  end
end

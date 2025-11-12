# frozen_string_literal: true

require "fileutils"
require "net/http"
require "uri"

module WhisperRuby
  ModelPaths = Struct.new(:asr, :vad, keyword_init: true)

  class ModelManager
    def ensure_all(whisper_config)
      asr_path = ensure_model(
        target_path: whisper_config.model_path,
        url: whisper_config.model_url,
        force_download: whisper_config.force_download
      )

      vad_path = ensure_model(
        target_path: whisper_config.vad_model_path,
        url: whisper_config.vad_model_url,
        force_download: whisper_config.force_download
      )

      ModelPaths.new(asr: asr_path, vad: vad_path)
    end

    private

    def ensure_model(target_path:, url:, force_download:)
      return target_path if File.file?(target_path) && !force_download

      FileUtils.mkdir_p(File.dirname(target_path))
      download_file(url, target_path)
    end

    def download_file(url, destination)
      tmp_path = "#{destination}.download"
      local_logger = defined?(LOGGER) ? LOGGER : nil
      local_logger&.info "Downloading model #{File.basename(destination)}"

      fetch_with_redirects(URI(url)) do |response|
        File.open(tmp_path, "wb") { |f| response.read_body { |chunk| f.write(chunk) } }
      end

      FileUtils.mv(tmp_path, destination)
      local_logger&.info "Model stored at #{destination}"
      destination
    ensure
      FileUtils.rm_f(tmp_path) if tmp_path && File.exist?(tmp_path)
    end

    def fetch_with_redirects(uri, limit = 5, &block)
      raise "Too many redirects while downloading #{uri}" if limit <= 0

      Net::HTTP.start(uri.host, uri.port, use_ssl: uri.scheme == "https") do |http|
        request = Net::HTTP::Get.new(uri)
        request["User-Agent"] = "whisper-ruby-service/1.0"

        http.request(request) do |response|
          case response
          when Net::HTTPRedirection
            next_uri = URI(response["location"])
            next_uri = uri + response["location"] if next_uri.relative?
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
end

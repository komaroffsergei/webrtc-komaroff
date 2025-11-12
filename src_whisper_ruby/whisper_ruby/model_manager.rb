# frozen_string_literal: true

require "fileutils"
require "net/http"
require "uri"

module WhisperRuby
  class ModelManager
    def asr_target_path(models_dir:, model_name:)
      File.join(models_dir, "ggml-#{model_name}.bin")
    end

    def vad_target_path(models_dir:, vad_model_name:)
      File.join(models_dir, "ggml-#{vad_model_name}.bin")
    end

    # Ensure ASR model is present; download if missing.
    def ensure_asr(models_dir:, model_name:)
      target = asr_target_path(models_dir:, model_name:)
      return target if File.file?(target)

      FileUtils.mkdir_p(File.dirname(target))
      url = asr_url_for(model_name)
      download_file(url, target)
    end

    # Ensure VAD model is present; download if missing.
    def ensure_vad(models_dir:, vad_model_name:)
      target = vad_target_path(models_dir:, vad_model_name:)
      return target if File.file?(target)

      FileUtils.mkdir_p(File.dirname(target))
      url = vad_url_for(vad_model_name)
      download_file(url, target)
    end

    private

    def asr_url_for(model_name)
      # Minimal mapping to official whisper.cpp HF repo naming
      "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-#{model_name}.bin"
    end

    def vad_url_for(vad_model_name)
      # VAD model follows ggml-silero-<version>.bin naming in the same repo
      "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-#{vad_model_name}.bin"
    end

    def download_file(url, destination)
      tmp_path = "#{destination}.download"
      local_logger = defined?(LOGGER) ? LOGGER : nil
      local_logger&.info "Downloading model #{File.basename(destination)} from #{url}"

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

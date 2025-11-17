# frozen_string_literal: true

require "faraday"
require "faraday/retry"
require "faraday/follow_redirects"
require "digest"
require "fileutils"

module WhisperRuby
  module ModelDownloader
    module_function

    TIMEOUT = 120
    OPEN_TIMEOUT = 20
    RETRIES = 5

    def faraday
      @faraday ||= Faraday.new do |f|
        f.request :retry,
                  max: RETRIES,
                  interval: 1,
                  interval_randomness: 0.2,
                  backoff_factor: 2

        f.response :follow_redirects

        f.options.timeout = TIMEOUT
        f.options.open_timeout = OPEN_TIMEOUT

        f.adapter :net_http
      end
    end

    def download_model(logger, model_url:, model_sha:, model_dir:, model_path:)
      FileUtils.mkdir_p(model_dir)

      # Если файл уже есть
      if File.exist?(model_path)
        if model_sha && Digest::SHA256.file(model_path).hexdigest == model_sha
          logger.log("Model exists (checksum OK)")
          return
        end

        logger.log("Checksum mismatch, removing old model")
        File.delete(model_path)
      end

      logger.log("Downloading model: #{model_url}")

      # Получаем Content-Length через HEAD-запрос
      head_response = faraday.head(model_url)
      total = head_response.headers["content-length"]&.to_i

      downloaded = 0
      last_percent = -1

      File.open(model_path, "wb") do |file|
        response = faraday.get(model_url) do |req|
          req.options.on_data = proc do |chunk, bytes_received|
            file.write(chunk)
            downloaded = bytes_received

            if total && total > 0
              percent = (downloaded * 100 / total).to_i
              if percent > last_percent
                logger.progress(percent)
                last_percent = percent
              end
            end
          end
        end

        unless response.success?
          logger.log("HTTP error #{response.status}", type: "error")
          raise "Failed to download model"
        end
      end

      if model_sha
        sha = Digest::SHA256.file(model_path).hexdigest
        if sha != model_sha
          logger.log("Checksum mismatch after download", type: "error")
          raise "Checksum mismatch"
        end
      end

      logger.log("Model downloaded successfully")
    rescue => e
      logger.log("Downloader error: #{e}", type: "error")
      raise
    end
  end
end
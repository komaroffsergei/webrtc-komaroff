# frozen_string_literal: true

require "digest"
require "fileutils"

module WhisperRuby
  module ModelDownloader
    module_function

    def download_model(logger, model_url:, model_sha:, model_dir:, model_path:)
      FileUtils.mkdir_p(model_dir)
      service = defined?(STACK_SERVICE_NAME) ? STACK_SERVICE_NAME : "whisper_ruby"

      # ------------------------------------------------------------
      # Existing file check
      # ------------------------------------------------------------
      if File.exist?(model_path)
        if model_sha && Digest::SHA1.file(model_path).hexdigest == model_sha
          logger.log("exists", type: "info", service: service, name: "model_downloading_status")
          return
        end

        logger.log("Checksum mismatch, removing file", type: "info",
                   service: service, name: "model_downloading_status")
        File.delete(model_path)
      end

      logger.log("downloading", type: "info", service: service, name: "model_downloading_status")

      # ------------------------------------------------------------
      # Determine total size
      # ------------------------------------------------------------
      total_size = `curl -sIL "#{model_url}" | grep -i Content-Length | tail -1 | awk '{print $2}'`.to_i
      total_size = nil if total_size == 0

      if total_size
        logger.log("size=#{total_size}", type: "info", service: service, name: "model_file_size")
      else
        logger.log("unable to detect file size", type: "warn", service: service)
      end

      # ------------------------------------------------------------
      # temp file path
      # ------------------------------------------------------------
      tmp = File.join(model_dir, ".download_#{Time.now.to_i}_#{rand(9999)}.bin")

      # ------------------------------------------------------------
      # Run curl async (background download)
      # ------------------------------------------------------------
      curl_cmd = [
        "curl",
        "-L",
        "-f",
        "--silent",
        "--show-error",
        "--retry", "5",
        "--retry-delay", "2",
        "-o", tmp,
        model_url
      ]

      curl_thread = Thread.new do
        system(*curl_cmd)
      end

      # ------------------------------------------------------------
      # Track progress every 100ms
      # ------------------------------------------------------------
      last_percent = -1

      until !curl_thread.alive?
        if total_size && File.exist?(tmp)
          downloaded = File.size(tmp)
          percent = (downloaded * 100 / total_size).to_i

          if percent != last_percent && percent >= 0 && percent <= 100
            logger.log(percent.to_s,
                       type: "info",
                       service: service,
                       name: "model_downloading_percent")

            last_percent = percent
          end
        end

        sleep 0.1
      end

      # ------------------------------------------------------------
      # Curl exit code
      # ------------------------------------------------------------
      unless File.exist?(tmp) && File.size(tmp) > 0
        raise "model was not downloaded"
      end

      # ------------------------------------------------------------
      # Checksum
      # ------------------------------------------------------------
      if model_sha
        actual_sha = Digest::SHA1.file(tmp).hexdigest
        if actual_sha != model_sha
          logger.log("Checksum mismatch: #{actual_sha} != #{model_sha}",
                     type: "error", service: service, name: "model_downloading_status")
          raise "Checksum mismatch"
        end
      end

      # ------------------------------------------------------------
      # Move to final path
      # ------------------------------------------------------------
      File.rename(tmp, model_path)

      logger.log("100", type: "info", service: service, name: "model_downloading_percent")
      logger.log("exists", type: "info", service: service, name: "model_downloading_status")

    rescue => e
      logger.log("Downloader error: #{e}", type: "error",
                 service: service, name: "model_downloading_status")
      raise
    ensure
      if defined?(tmp) && File.exist?(tmp)
        begin
          File.delete(tmp)
        rescue => e
          logger.log("Could not delete temp file: #{e}", type: "warn", service: service)
        end
      end
    end
  end
end

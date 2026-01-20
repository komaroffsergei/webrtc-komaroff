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
          logger.command("status_asr", { status: "ready" }, service: service)
          return
        end

        logger.info("Checksum mismatch, removing file", service: service)
        File.delete(model_path)
      end

      logger.command("status_asr", { status: "downloading", percent: 0 }, service: service)

      # ------------------------------------------------------------
      # Determine total size
      # ------------------------------------------------------------
      total_size = `curl -sIL "#{model_url}" | grep -i Content-Length | tail -1 | awk '{print $2}'`.to_i
      total_size = nil if total_size == 0

      if total_size
        logger.info("size=#{total_size}", service: service, name: "model_file_size")
      else
        logger.info("unable to detect file size", service: service)
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
            logger.command("status_asr", { status: "downloading", percent: percent }, service: service)

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
          logger.error("Checksum mismatch: #{actual_sha} != #{model_sha}", service: service)
          raise "Checksum mismatch"
        end
      end

      # ------------------------------------------------------------
      # Move to final path
      # ------------------------------------------------------------
      File.rename(tmp, model_path)

      logger.command("status_asr", { status: "downloading", percent: 100 }, service: service)
      logger.command("status_asr", { status: "ready" }, service: service)

    rescue => e
      logger.error("Downloader error: #{e}", service: service)
      raise
    # ensure
      # if defined?(tmp) && File.exist?(tmp)
      #   begin
      #     File.delete(tmp)
      #   rescue => e
      #     logger.log("Could not delete temp file: #{e}", type: "warn", service: service)
      #   end
      # end
    end
  end
end

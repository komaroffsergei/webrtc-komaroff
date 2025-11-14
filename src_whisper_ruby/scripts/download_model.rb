#!/usr/bin/env ruby
# frozen_string_literal: true

require "bundler/setup"
require "optparse"
require "logger"
require "ostruct"

$LOAD_PATH.unshift(File.expand_path("..", __dir__))
require "whisper_ruby"

options = {
  model: ENV["WHISPER_MODEL_NAME"],
  models_dir: ENV["MODELS_DIR"],
  vad_model: ENV["WHISPER_VAD_MODEL_NAME"],
  force: false
}

OptionParser.new do |parser|
  parser.banner = "Usage: download_model.rb [options]"

  parser.on("--model=NAME", "ASR model name (default: medium)") { |value| options[:model] = value }
  parser.on("--models-dir=DIR", "Directory to store models") { |value| options[:models_dir] = value }
  parser.on("--vad-model=NAME", "VAD model name (default: silero-v5.1.2)") { |value| options[:vad_model] = value }
  parser.on("--force", "Force re-download even if files exist") { options[:force] = true }
end.parse!

ENV["WHISPER_MODEL_NAME"] = options[:model] if options[:model]
ENV["MODELS_DIR"] = options[:models_dir] if options[:models_dir]
ENV["WHISPER_VAD_MODEL_NAME"] = options[:vad_model] if options[:vad_model]
ENV["WHISPER_FORCE_DOWNLOAD"] = "1" if options[:force]

logger = Logger.new($stdout)
logger.level = Logger::INFO

def truthy?(value)
  return false if value.nil?
  !%w[0 false no off].include?(value.to_s.strip.downcase)
end

def default_model_filename(name)
  base = name.dup
  base += ".bin" unless base.end_with?(".bin")
  base.start_with?("ggml-") ? base : "ggml-#{base}"
end

def default_vad_filename(name)
  return name if name&.end_with?(".bin")
  "ggml-#{name}.bin"
end

models_dir = ENV.fetch("MODELS_DIR", File.expand_path("../../models", __dir__))

whisper_config = OpenStruct.new(
  model_path: ENV["WHISPER_MODEL"],
  model_name: ENV["WHISPER_MODEL_NAME"] || "medium",
  model_url: ENV["WHISPER_MODEL_URL"],
  models_dir: models_dir,
  vad_model_path: ENV["WHISPER_VAD_MODEL_PATH"],
  vad_model_name: ENV["WHISPER_VAD_MODEL_NAME"] || "silero-v5.1.2",
  force_download: truthy?(ENV["WHISPER_FORCE_DOWNLOAD"]),
  logger: logger
)

whisper_config.define_singleton_method(:resolved_model_reference) do
  path = model_path.to_s.strip
  return path unless path.empty?
  File.join(models_dir, default_model_filename((model_name || "medium").to_s))
end

whisper_config.define_singleton_method(:resolved_vad_reference) do
  path = vad_model_path.to_s.strip
  return path unless path.empty?
  File.join(models_dir, default_vad_filename((vad_model_name || "silero-v5.1.2").to_s))
end

# Ensure concrete paths for download manager
whisper_config.model_path = whisper_config.resolved_model_reference
whisper_config.vad_model_path = whisper_config.resolved_vad_reference

manager = WhisperRuby::ModelManager.new()
paths = manager.ensure_all(whisper_config)

logger.info("ASR model ready at #{paths.asr}")
logger.info("VAD model ready at #{paths.vad}")

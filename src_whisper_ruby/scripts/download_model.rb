#!/usr/bin/env ruby
# frozen_string_literal: true

require "bundler/setup"
require "optparse"
require "logger"

$LOAD_PATH.unshift(File.expand_path("../lib", __dir__))
require "whisper_ruby"

options = {
  model: ENV["WHISPER_MODEL_NAME"],
  models_dir: ENV["WHISPER_MODELS_DIR"],
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
ENV["WHISPER_MODELS_DIR"] = options[:models_dir] if options[:models_dir]
ENV["WHISPER_VAD_MODEL_NAME"] = options[:vad_model] if options[:vad_model]
ENV["WHISPER_FORCE_DOWNLOAD"] = "1" if options[:force]

logger = Logger.new($stdout)
logger.level = Logger::INFO

config = WhisperRuby::WhisperConfig.from_env
manager = WhisperRuby::ModelManager.new(logger: logger)
paths = manager.ensure_all(config)

logger.info("ASR model ready at #{paths.asr}")
logger.info("VAD model ready at #{paths.vad}")

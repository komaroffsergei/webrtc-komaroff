# frozen_string_literal: true

ENV["APP_ENV"] ||= ENV["RACK_ENV"] || "development"

require "bundler/setup"

$LOAD_PATH.unshift(File.expand_path("lib", __dir__))
require "whisper_ruby"

run WhisperRuby::Application.build

# frozen_string_literal: true

require "simplecov"
SimpleCov.start

require "rspec"

ENV["APP_ENV"] = "test"
ENV["RACK_ENV"] = "test"
ENV["WHISPER_SERVICE_DISABLED"] = "1"

RSpec.configure do |config|
  # Enable more verbose output
  config.formatter = :documentation if ENV['VERBOSE']
end

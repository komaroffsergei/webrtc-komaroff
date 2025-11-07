# frozen_string_literal: true

require "simplecov"
SimpleCov.start

require "rack/test"
require "rspec"
require "rack/builder"

ENV["APP_ENV"] = "test"
ENV["RACK_ENV"] = "test"
ENV["WHISPER_SERVICE_DISABLED"] = "1"

module Rack::Test::AppHelper
  def app
    RSpec.configuration.app
  end
end

RSpec.configure do |config|
  config.include Rack::Test::Methods
  config.include Rack::Test::AppHelper
  config.add_setting :app

  config.before(:suite) do
    rack_app, = Rack::Builder.parse_file(File.expand_path("../config.ru", __dir__))
    RSpec.configuration.app = rack_app
  end
end

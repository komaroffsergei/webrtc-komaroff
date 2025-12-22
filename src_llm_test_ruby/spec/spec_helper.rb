# frozen_string_literal: true

ENV['RACK_ENV'] = 'test'

require 'rspec'
require 'rack/test'

require_relative '../service/service'

RSpec.configure do |config|
  config.include Rack::Test::Methods

  config.before(:suite) do
    # Настройка тестовых данных
  end
end
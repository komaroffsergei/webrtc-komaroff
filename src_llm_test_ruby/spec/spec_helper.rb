# frozen_string_literal: true

ENV['RACK_ENV'] = 'test'
ENV['DEBUG'] = 'false'

require 'rspec'

require_relative '../service/service'
require_relative '../service/db'
require_relative '../service/mcp_tools'
require_relative '../service/utils'

RSpec.configure do |config|
  config.order = :random

  config.before do
    LLMTestRuby::DB.reset!
  end
end

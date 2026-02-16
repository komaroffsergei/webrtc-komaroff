# frozen_string_literal: true

require 'dotenv/load'

module LLMTestRuby
  module Settings
    USER_ID = ENV['USER_ID'] || 'user123'
    OLLAMA_URL = ENV['OLLAMA_URL'] || 'http://192.168.2.108:11435'
    DEBUG = (ENV['DEBUG'] || 'true').casecmp?('true')
    MAX_STEPS = (ENV['AGENT_MAX_STEPS'] || '10').to_i
  end
end

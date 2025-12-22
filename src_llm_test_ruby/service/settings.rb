# frozen_string_literal: true

require 'dotenv/load'

module LLMTestRuby
  module Settings
    USER_ID = ENV.fetch('USER_ID', 'user123')
    OLLAMA_URL = ENV.fetch('OLLAMA_URL', 'http://192.168.2.108:11435')
    DEBUG = ENV.fetch('DEBUG', 'true').casecmp?('true')
    MAX_STEPS = ENV.fetch('AGENT_MAX_STEPS', '10').to_i
  end
end

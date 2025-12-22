# frozen_string_literal: true

require 'spec_helper'

RSpec.describe LLMTestRuby::Service do
  let(:service) { described_class.new }

  # "qwen3:0.6b",
  #   "qwen2.5:7b",
  #   "qwen3:1.7b",

  describe 'integration' do
    it 'processes a simple query' do
      query = "Найди аэропорт в радиусе 250 км с самой короткой ВПП"
      response = service.run_model('qwen3:0.6b', query)

      expect(response).to be_a(String)
      expect(response).not_to be_empty
    end
  end
end